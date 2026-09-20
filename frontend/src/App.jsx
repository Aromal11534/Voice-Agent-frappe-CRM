import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CircleAlert, Clock3, Flame, Menu, Phone, RefreshCw, Search, Users, HelpCircle, ChevronDown, X
} from 'lucide-react';
import BrowserPhone from './components/BrowserPhone';
import Sidebar from './components/Sidebar';
import AuthPage from './components/AuthPage';
import MetricCard from './components/MetricCard';
import CallRow from './components/CallRow';
import CallDetail from './components/CallDetail';
import LeadsView from './components/LeadsView';
import { formatDuration } from './utils/formatters';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const VALID_PAGES = new Set(['overview', 'calls', 'leads', 'simulate']);
const FILTER_TIME_ANCHOR = Date.now();

function pageFromHash() {
  const page = window.location.hash.replace('#', '');
  return VALID_PAGES.has(page) ? page : 'overview';
}

function App() {
  const [stats, setStats] = useState(null);
  const [calls, setCalls] = useState([]);
  const [health, setHealth] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('All');
  const [query, setQuery] = useState('');
  const [period, setPeriod] = useState('30');
  const [direction, setDirection] = useState('all');
  const [token, setToken] = useState(() => sessionStorage.getItem('voiceAgentToken') || '');
  
  // Auth State
  const [authView, setAuthView] = useState(() => {
    return sessionStorage.getItem('voiceAgentToken') ? null : 'login';
  });
  
  const [mobileNav, setMobileNav] = useState(false);
  const [activePage, setActivePage] = useState(pageFromHash);

  const apiFetch = useCallback(async (path) => {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (response.status === 401) {
      setAuthView('login');
      throw new Error('Access token required');
    }
    if (!response.ok) throw new Error(`Request failed (${response.status})`);
    return response.json();
  }, [token]);

  const loadDashboard = useCallback(async (quiet = false) => {
    if (authView) return; // Don't load if not authenticated
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const [statsData, callsData, healthData] = await Promise.all([
        apiFetch('/api/stats'),
        apiFetch('/api/calls?limit=50'),
        fetch(`${API_BASE}/health`).then((res) => res.json()),
      ]);
      setStats(statsData);
      setCalls(callsData.calls || []);
      setHealth(healthData);
    } catch (err) {
      setError(err.message || 'Unable to load dashboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [apiFetch, authView]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => loadDashboard(), 0);
    const interval = window.setInterval(() => loadDashboard(true), 30_000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadDashboard]);

  useEffect(() => {
    const handleHashChange = () => setActivePage(pageFromHash());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const selectCall = async (callId) => {
    setSelectedId(callId);
    setDetailLoading(true);
    setDetail(null);
    try {
      const data = await apiFetch(`/api/calls/${callId}`);
      setDetail(data.call);
    } catch (err) {
      setError(err.message || 'Unable to load call details');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAuth = async (email, password) => {
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!response.ok) {
        throw new Error('Invalid email or password');
      }
      const data = await response.json();
      const clean = data.token.trim();
      sessionStorage.setItem('voiceAgentToken', clean);
      setToken(clean);
      setAuthView(null);
    } catch (err) {
      alert(err.message);
    }
  };

  const clearHistory = async () => {
    if (!window.confirm("Are you sure you want to delete ALL call and lead history? This cannot be undone.")) return;
    try {
      const response = await fetch(`${API_BASE}/api/calls`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error('Failed to delete history');
      loadDashboard();
    } catch (err) {
      setError(err.message || "Failed to clear history");
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem('voiceAgentToken');
    setToken('');
    setAuthView('login');
  };

  const visibleCalls = useMemo(() => calls.filter((call) => {
    const category = call.lead_status || call.status || '';
    const matchesFilter = filter === 'All' || category.toLowerCase() === filter.toLowerCase();
    const callTime = call.start_time ? new Date(call.start_time).getTime() : 0;
    const cutoff = period === 'all' ? 0 : FILTER_TIME_ANCHOR - Number(period) * 24 * 60 * 60 * 1000;
    const matchesPeriod = period === 'all' || callTime >= cutoff;
    const matchesDirection = direction === 'all' || call.direction === direction;
    const haystack = `${call.caller_number || ''} ${call.extracted_data?.name || ''} ${call.extracted_data?.intent || ''}`.toLowerCase();
    return matchesFilter && matchesPeriod && matchesDirection && haystack.includes(query.toLowerCase());
  }), [calls, direction, filter, period, query]);

  const visibleLeads = useMemo(
    () => visibleCalls.filter((call) => call.lead_status || call.extracted_data),
    [visibleCalls],
  );

  const navigateTo = (page) => {
    window.location.hash = page;
    setActivePage(page);
    setMobileNav(false);
  };

  const openLeadCall = (callId) => {
    navigateTo('calls');
    selectCall(callId);
  };

  const extractionTotal = (stats?.frappe_synced || 0) + (stats?.frappe_pending || 0);
  const isHealthy = health?.status === 'ok';

  if (authView) {
    return <AuthPage view={authView} setView={setAuthView} onAuth={handleAuth} />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-white font-sans text-gray-900">
      <Sidebar open={mobileNav} onClose={() => setMobileNav(false)} activePage={activePage} onNavigate={navigateTo} />

      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        
        {/* Top Navbar */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 sm:px-6">
          <div className="flex items-center flex-1">
            <button className="text-gray-500 hover:text-gray-700 md:hidden mr-4" onClick={() => setMobileNav(true)}>
              <Menu className="h-5 w-5" />
            </button>
            
            {/* Search Bar matching image */}
            <div className="hidden sm:flex items-center bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 w-80 focus-within:bg-white focus-within:ring-1 focus-within:ring-gray-300">
              <Search className="h-4 w-4 text-gray-400 mr-2" />
              <input 
                type="text" 
                placeholder="Search" 
                className="bg-transparent border-none outline-none text-sm w-full placeholder-gray-400"
              />
              <div className="flex items-center gap-1 ml-2">
                <kbd className="bg-white border border-gray-200 rounded px-1.5 text-[10px] font-sans text-gray-500 shadow-sm">⌘</kbd>
                <kbd className="bg-white border border-gray-200 rounded px-1.5 text-[10px] font-sans text-gray-500 shadow-sm">F</kbd>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <button 
              onClick={handleLogout} 
              className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
            >
              Logout
            </button>
          </div>
        </header>

        {/* Page Title Bar */}
        <div className="border-b border-gray-200 bg-white px-4 sm:px-8 py-5 shrink-0 flex justify-between items-center">
          <h1 className="text-xl font-semibold text-gray-900 tracking-tight">
            {activePage === 'overview' ? 'Dashboard' : activePage === 'calls' ? 'Call Logs' : activePage === 'leads' ? 'Leads' : 'Simulate Call'}
          </h1>
          <div className="flex items-center gap-3">
              <button onClick={clearHistory} className="text-xs text-red-600 hover:text-red-800 font-medium px-3 py-1.5 border border-red-200 rounded bg-red-50 hover:bg-red-100 transition-colors">
                Clear History
              </button>
              <div className={`hidden sm:flex items-center gap-2 rounded px-2.5 py-1 text-xs font-medium border ${isHealthy ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${isHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
                {isHealthy ? 'API Ready' : 'Setup required'}
              </div>
              <button className="p-1.5 text-gray-400 hover:text-gray-800 rounded hover:bg-gray-100 transition-colors border border-transparent disabled:opacity-50" onClick={() => loadDashboard(true)} disabled={refreshing}>
                <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
          </div>
        </div>

        {/* Main Canvas */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-[#fafafa]">
          <div key={activePage} className="w-full space-y-6 page-transition">
            
            {error && (
              <div className="rounded border border-red-200 bg-red-50 p-4">
                <div className="flex">
                  <CircleAlert className="h-5 w-5 text-red-500" />
                  <div className="ml-3 flex-1 md:flex md:justify-between">
                    <p className="text-sm text-red-800">{error}</p>
                    <p className="mt-2 text-sm md:mt-0 md:ml-6">
                      <button onClick={() => loadDashboard()} className="whitespace-nowrap font-medium text-red-800 hover:text-red-700">Try again &rarr;</button>
                    </p>
                  </div>
                </div>
              </div>
            )}

            {activePage === 'overview' && (
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard 
                  label="Total Calls" 
                  value={stats?.total_calls || 0} 
                  detail={<span><strong>{stats?.today_calls || 0}</strong> Today</span>} 
                  icon={Phone} 
                  loading={loading} 
                />
                <MetricCard 
                  label="Qualified Leads" 
                  value={extractionTotal} 
                  detail={<span><strong>{stats?.frappe_synced || 0}</strong> Delivered</span>} 
                  icon={Users} 
                  loading={loading} 
                />
                <MetricCard 
                  label="Hot Leads" 
                  value={stats?.by_lead_status?.Hot || 0} 
                  detail={<span><strong>{stats?.by_lead_status?.Warm || 0}</strong> Warm</span>} 
                  icon={Flame} 
                  loading={loading} 
                />
                <MetricCard 
                  label="Average Call" 
                  value={formatDuration(stats?.avg_duration_sec || 0)} 
                  detail={<span>Conversation time</span>} 
                  icon={Clock3} 
                  loading={loading} 
                />
              </div>
            )}

            {activePage === 'simulate' && (
              <div className="flex items-center justify-center h-[calc(100vh-20rem)]">
                <BrowserPhone />
              </div>
            )}

            {activePage !== 'leads' && activePage !== 'simulate' && (
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 flex flex-col bg-white border border-gray-200 rounded-md shadow-sm overflow-hidden min-h-[500px]">
                  <div className="px-5 py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">Recent Calls</h3>
                      <p className="text-xs text-gray-500 mt-0.5">{visibleCalls.length} records found</p>
                    </div>
                    
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <select 
                          className="pl-3 pr-8 py-1.5 text-xs border border-gray-200 rounded-md bg-white focus:outline-none focus:border-gray-400 appearance-none text-gray-700"
                          value={period} onChange={(e) => setPeriod(e.target.value)}
                        >
                          <option value="7">Last 7 Days</option>
                          <option value="30">Last 30 Days</option>
                          <option value="all">All Time</option>
                        </select>
                        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
                      </div>

                      <div className="relative">
                        <select
                          className="pl-3 pr-8 py-1.5 text-xs border border-gray-200 rounded-md bg-white focus:outline-none focus:border-gray-400 appearance-none text-gray-700"
                          value={direction}
                          onChange={(event) => setDirection(event.target.value)}
                        >
                          <option value="all">All directions</option>
                          <option value="inbound">Inbound</option>
                          <option value="outbound">Outbound</option>
                        </select>
                        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400 pointer-events-none" />
                      </div>
                      
                      <div className="relative max-w-xs w-full">
                        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-2.5">
                          <Search className="h-3.5 w-3.5 text-gray-400" />
                        </div>
                        <input
                          type="text"
                          className="block w-full rounded-md border border-gray-200 py-1.5 pl-8 pr-3 text-xs text-gray-900 placeholder:text-gray-400 focus:border-gray-400 focus:outline-none"
                          placeholder="Search..."
                          value={query} onChange={(e) => setQuery(e.target.value)}
                        />
                        {query && (
                          <button className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-gray-400 hover:text-gray-600" onClick={() => setQuery('')}>
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div className="px-5 py-2.5 border-b border-gray-100 bg-white flex gap-2 overflow-x-auto">
                    {['All', 'Hot', 'Warm', 'Cold', 'Not Interested'].map((item) => (
                      <button
                        key={item}
                        onClick={() => setFilter(item)}
                        className={`whitespace-nowrap rounded px-2.5 py-1 text-xs font-medium transition-colors ${filter === item ? 'bg-gray-100 text-gray-900' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'}`}
                      >
                        {item}
                      </button>
                    ))}
                  </div>

                  <div className="flex-1 overflow-y-auto">
                    {loading ? (
                      <div className="divide-y divide-gray-100">
                        {[1, 2, 3, 4, 5].map(i => (
                          <div key={i} className="px-5 py-4 animate-pulse flex gap-4">
                            <div className="h-8 w-8 bg-gray-100 rounded" />
                            <div className="flex-1 space-y-2 py-1">
                              <div className="h-2.5 bg-gray-200 rounded w-1/4"></div>
                              <div className="h-2 bg-gray-100 rounded w-1/2"></div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : visibleCalls.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
                        <div className="h-10 w-10 bg-gray-50 rounded-full flex items-center justify-center mb-3 border border-gray-100">
                          <Search className="h-4 w-4 text-gray-400" />
                        </div>
                        <h3 className="text-sm font-medium text-gray-900">No calls found</h3>
                        <p className="mt-1 text-xs text-gray-500">Try adjusting your filters.</p>
                        <button onClick={() => { setQuery(''); setFilter('All'); }} className="mt-3 text-xs font-medium text-gray-900 underline hover:text-black">Reset</button>
                      </div>
                    ) : (
                      <ul className="divide-y divide-gray-100">
                        {visibleCalls.map((call) => (
                          <CallRow key={call.id} call={call} active={selectedId === call.id} onSelect={() => selectCall(call.id)} />
                        ))}
                      </ul>
                    )}
                  </div>
                </div>

                <div className="hidden xl:block xl:col-span-1">
                  <CallDetail call={detail} loading={detailLoading} onClose={() => { setSelectedId(null); setDetail(null); }} />
                </div>
              </div>
            )}

            {activePage === 'leads' && (
              <LeadsView leads={visibleLeads} loading={loading} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter} onOpenCall={openLeadCall} />
            )}
            
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
