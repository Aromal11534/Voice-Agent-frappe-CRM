import { Clock3 } from 'lucide-react';
import { initials, formatDuration, formatDate } from '../utils/formatters';
import StatusBadge from './StatusBadge';

export default function CallRow({ call, active, onSelect }) {
  const name = call.extracted_data?.name || 'Unknown caller';
  
  return (
    <li className={`group cursor-pointer hover:bg-gray-50 transition-colors ${active ? 'bg-gray-50/80 relative' : ''}`} onClick={onSelect}>
      {active && <div className="absolute inset-y-0 left-0 w-0.5 bg-gray-900" />}
      <div className="flex items-center gap-4 px-5 py-3">
        <div className="h-8 w-8 rounded bg-gray-100 border border-gray-200 flex items-center justify-center text-xs font-semibold text-gray-600 shrink-0">
          {initials(name)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <p className="truncate text-sm font-medium text-gray-900">{name}</p>
            <div className="ml-2 flex flex-shrink-0">
              <StatusBadge value={call.lead_status || call.status} />
            </div>
          </div>
          <div className="flex items-center justify-between mt-0.5">
            <div className="flex items-center text-xs text-gray-500 gap-3">
              <span className="truncate">{call.caller_number || 'Number unavailable'}</span>
              <span className="flex items-center gap-1"><Clock3 className="h-3 w-3" /> {formatDuration(call.duration_sec)}</span>
            </div>
            <div className="text-[11px] text-gray-400">{formatDate(call.start_time)}</div>
          </div>
        </div>
      </div>
    </li>
  );
}
