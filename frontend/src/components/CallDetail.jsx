import { MessageSquareText, X } from 'lucide-react';
import { initials, formatDuration } from '../utils/formatters';
import StatusBadge from './StatusBadge';

export default function CallDetail({ call, loading, onClose }) {
  if (!call && !loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-md shadow-sm h-full min-h-[500px] flex flex-col items-center justify-center p-8 text-center">
        <div className="h-10 w-10 bg-gray-50 rounded-full flex items-center justify-center mb-3 border border-gray-100">
          <MessageSquareText className="h-4 w-4 text-gray-400" />
        </div>
        <h3 className="text-sm font-medium text-gray-900">No conversation selected</h3>
        <p className="mt-1 text-xs text-gray-500 max-w-xs">Select a call from the feed to view its details.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-md shadow-sm h-full min-h-[500px] p-5">
        <div className="animate-pulse space-y-6">
          <div className="flex gap-3 items-center">
            <div className="h-10 w-10 bg-gray-100 rounded" />
            <div className="space-y-2 flex-1">
              <div className="h-3 bg-gray-200 rounded w-1/3" />
              <div className="h-2 bg-gray-100 rounded w-1/4" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="h-12 bg-gray-50 rounded" />
            <div className="h-12 bg-gray-50 rounded" />
          </div>
          <div className="h-20 bg-gray-50 rounded" />
          <div className="h-32 bg-gray-50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-md shadow-sm h-full min-h-[500px] flex flex-col max-h-[calc(100vh-18rem)]">
      <div className="border-b border-gray-100 px-5 py-4 flex items-center justify-between sticky top-0 bg-white z-10">
        <h3 className="text-sm font-semibold text-gray-900">Call Details</h3>
        <button className="text-gray-400 hover:text-gray-900 transition-colors xl:hidden" onClick={onClose}>
          <X className="h-4 w-4" />
        </button>
      </div>
      
      <div className="overflow-y-auto p-5 flex-1 space-y-6">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded bg-gray-100 border border-gray-200 flex items-center justify-center text-sm font-bold text-gray-700">
            {initials(call.extracted_data?.name)}
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-base font-semibold text-gray-900 truncate">{call.extracted_data?.name || 'Unknown caller'}</h4>
            <p className="text-xs text-gray-500 truncate">{call.caller_number}</p>
          </div>
          <StatusBadge value={call.lead_status || call.status} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <MiniFact label="Duration" value={formatDuration(call.duration_sec)} />
          <MiniFact label="Language" value={call.extracted_data?.language || call.detected_lang || 'Auto'} />
        </div>

        {call.extracted_data?.summary && (
          <div className="rounded border border-gray-100 bg-gray-50/50 p-4">
            <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">Summary</h4>
            <p className="text-xs text-gray-700 leading-relaxed">{call.extracted_data.summary}</p>
          </div>
        )}

        <div>
          <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-3">Qualification</h4>
          <dl className="space-y-2">
            <InfoRow label="Intent" value={call.extracted_data?.intent} />
            <InfoRow label="Requirement" value={call.extracted_data?.requirement} />
            <InfoRow label="Budget" value={call.extracted_data?.budget ? `₹${Number(call.extracted_data.budget).toLocaleString('en-IN')}` : null} />
            <InfoRow label="Timeline" value={call.extracted_data?.timeline} />
          </dl>
        </div>

        <div>
          <div className="flex items-center justify-between mb-3">
             <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Transcript</h4>
             <span className="text-[10px] text-gray-400 font-medium bg-gray-100 px-1.5 py-0.5 rounded">{call.transcript?.length || 0} turns</span>
          </div>
          
          <div className="space-y-4">
            {call.transcript?.length ? (
              call.transcript.map((turn, index) => <TranscriptTurn key={`${turn.timestamp}-${index}`} turn={turn} />)
            ) : (
              <p className="text-xs text-gray-500 italic py-4">No transcript captured.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TranscriptTurn({ turn }) {
  const caller = turn.role === 'caller';
  return (
    <div className={`flex flex-col mb-4 ${caller ? 'items-start' : 'items-end'}`}>
      <span className="text-[10px] font-medium text-gray-400 mb-1 px-1">{caller ? 'Caller' : 'AI'}</span>
      <div className={`px-3 py-2 text-xs rounded-md max-w-[90%] border ${caller ? 'bg-white text-gray-900 border-gray-200' : 'bg-gray-100 text-gray-900 border-gray-200'}`}>
        {turn.text}
      </div>
    </div>
  );
}

function MiniFact({ label, value }) { 
  return (
    <div className="rounded border border-gray-100 bg-white p-3 text-left">
      <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">{label}</span>
      <strong className="block text-sm font-medium text-gray-900 mt-0.5 truncate">{value || '—'}</strong>
    </div>
  ); 
}

function InfoRow({ label, value }) { 
  if (!value) return null;
  return (
    <div className="flex py-1 text-xs">
      <dt className="w-24 text-gray-500 font-medium">{label}</dt>
      <dd className="flex-1 text-gray-900">{value}</dd>
    </div>
  );
}
