import { Activity, Phone, Users, Mic, FileText, ChevronDown, PanelLeftClose, ArrowUpRight } from 'lucide-react';
import kiduLogo from '../assets/kiducrm.png';

function NavItem({ id, icon: Icon, label, isActive, isExternal = false, href, onNavigate }) {
  return (
    <a
      href={href || `#${id}`}
      target={isExternal ? "_blank" : "_self"}
      rel={isExternal ? "noreferrer" : undefined}
      onClick={(event) => {
        if (!isExternal) {
          event.preventDefault();
          onNavigate(id);
        }
      }}
      className={`group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-all duration-300 ease-out mb-0.5 ${
        isActive
          ? 'bg-gray-200/60 text-gray-900 font-medium'
          : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100/50'
      }`}
    >
      <Icon className={`h-4 w-4 flex-shrink-0 transition-colors duration-300 ${isActive ? 'text-gray-900' : 'text-gray-400 group-hover:text-gray-600'}`} strokeWidth={isActive ? 2 : 1.5} />
      {label}
      {isExternal && <ArrowUpRight className="ml-auto h-3.5 w-3.5 text-gray-400" />}
    </a>
  );
}

export default function Sidebar({ open, onClose, activePage, onNavigate }) {

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div className="fixed inset-0 z-40 bg-gray-900/40 md:hidden" onClick={onClose} aria-hidden="true" />
      )}
      
      {/* Sidebar component */}
      <div className={`fixed inset-y-0 left-0 z-50 w-[240px] bg-[#f8f9fa] border-r border-gray-200 transform transition-transform duration-200 ease-in-out md:static md:translate-x-0 flex flex-col ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        
        {/* Logo Area */}
        <div className="flex h-16 shrink-0 items-center justify-between px-6 mb-2 mt-2">
          <img src={kiduLogo} alt="LOGO" className="h-8 object-contain" />
          <button className="flex h-5 w-5 items-center justify-center rounded bg-gray-200/60 text-gray-500 hover:text-gray-900 hover:bg-gray-300/50 transition-colors">
            <PanelLeftClose className="h-3.5 w-3.5" />
          </button>
        </div>
        
        <nav className="flex-1 overflow-y-auto px-3 py-2 scrollbar-hide">
          
          <div className="mb-6">
            <NavItem id="overview" icon={Activity} label="Dashboard" isActive={activePage === 'overview'} onNavigate={onNavigate} />
            <NavItem id="calls" icon={Phone} label="Calls" isActive={activePage === 'calls'} onNavigate={onNavigate} />
            <NavItem id="leads" icon={Users} label="Leads" isActive={activePage === 'leads'} onNavigate={onNavigate} />
            <NavItem id="simulate" icon={Mic} label="Simulate Call" isActive={activePage === 'simulate'} onNavigate={onNavigate} />
          </div>
          
          <div className="mb-6">
            <NavItem id="docs" href="/docs" isExternal={true} icon={FileText} label="API Docs" isActive={false} />
          </div>

        </nav>
        
        {/* Profile Footer */}
        <div className="p-4 border-t border-gray-200 flex items-center justify-between cursor-pointer hover:bg-gray-100/50 transition-colors">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded bg-gray-200 flex items-center justify-center text-[10px] font-bold text-gray-700">M</div>
            <span className="text-sm font-medium text-gray-900">Marketing Team's</span>
          </div>
          <ChevronDown className="h-4 w-4 text-gray-500" />
        </div>
      </div>
    </>
  );
}
