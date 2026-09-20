import { Search } from 'lucide-react';
import StatusBadge from './StatusBadge';

export default function LeadsView({ leads, loading, query, setQuery, filter, setFilter, onOpenCall }) {
  return (
    <div className="bg-white border border-gray-200 rounded-md shadow-sm overflow-hidden h-[calc(100vh-14rem)] flex flex-col">
      <div className="px-5 py-4 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Database Summaries</h3>
        </div>
        <div className="relative max-w-sm w-full">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <Search className="h-3.5 w-3.5 text-gray-400" />
          </div>
          <input
            type="text"
            className="block w-full rounded-md border border-gray-200 py-1.5 pl-9 pr-3 text-xs text-gray-900 focus:outline-none focus:border-gray-400 placeholder:text-gray-400"
            placeholder="Search database..."
            value={query} onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>
      
      <div className="px-5 py-2.5 border-b border-gray-100 bg-white flex gap-2 overflow-x-auto shrink-0">
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
      
      <div className="flex-1 overflow-auto">
        <table className="min-w-full divide-y divide-gray-100">
          <thead className="bg-white sticky top-0 z-10">
            <tr>
              <th scope="col" className="py-3 pl-5 pr-3 text-left text-[10px] font-bold uppercase tracking-widest text-gray-400">Lead</th>
              <th scope="col" className="px-3 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-gray-400 hidden sm:table-cell">Intent</th>
              <th scope="col" className="px-3 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-gray-400 hidden md:table-cell">Budget</th>
              <th scope="col" className="px-3 py-3 text-left text-[10px] font-bold uppercase tracking-widest text-gray-400">Status</th>
              <th scope="col" className="relative py-3 pl-3 pr-5"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {loading ? (
              [1, 2, 3, 4].map(i => (
                <tr key={i} className="animate-pulse">
                  <td className="py-4 pl-5 pr-3"><div className="h-3 w-32 bg-gray-100 rounded mb-2" /><div className="h-2 w-24 bg-gray-50 rounded" /></td>
                  <td className="px-3 py-4 hidden sm:table-cell"><div className="h-3 w-24 bg-gray-100 rounded" /></td>
                  <td className="px-3 py-4 hidden md:table-cell"><div className="h-3 w-16 bg-gray-100 rounded" /></td>
                  <td className="px-3 py-4"><div className="h-4 w-16 bg-gray-200 rounded" /></td>
                  <td className="py-4 pl-3 pr-5 text-right"><div className="h-4 w-12 bg-gray-100 rounded inline-block" /></td>
                </tr>
              ))
            ) : leads.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center">
                  <span className="text-sm text-gray-500">No records available</span>
                </td>
              </tr>
            ) : leads.map((lead) => (
              <tr key={lead.id} className="hover:bg-gray-50 transition-colors">
                <td className="whitespace-nowrap py-3 pl-5 pr-3">
                  <div className="font-medium text-sm text-gray-900">{lead.extracted_data?.name || 'Unknown caller'}</div>
                  <div className="text-gray-400 text-xs mt-0.5">{lead.caller_number || 'Number unavailable'}</div>
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-xs text-gray-600 hidden sm:table-cell">{lead.extracted_data?.intent || 'Not specified'}</td>
                <td className="whitespace-nowrap px-3 py-3 text-xs text-gray-600 hidden md:table-cell">{lead.extracted_data?.budget ? `₹${Number(lead.extracted_data.budget).toLocaleString('en-IN')}` : '—'}</td>
                <td className="whitespace-nowrap px-3 py-3"><StatusBadge value={lead.lead_status || 'Cold'} /></td>
                <td className="relative whitespace-nowrap py-3 pl-3 pr-5 text-right font-medium">
                  <button onClick={() => onOpenCall(lead.id)} className="text-xs text-gray-500 hover:text-black hover:underline">
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
