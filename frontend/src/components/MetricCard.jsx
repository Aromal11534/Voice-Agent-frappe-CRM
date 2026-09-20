import { ChevronRight } from 'lucide-react';

export default function MetricCard({ label, value, detail, loading }) {
  return (
    <div className="rounded-md bg-white p-5 border border-gray-200 shadow-sm flex flex-col justify-between">
      <div>
        <p className="text-xs font-medium text-gray-400 mb-2">{label}</p>
        {loading ? (
          <div className="h-8 w-20 bg-gray-100 rounded animate-pulse" />
        ) : (
          <h4 className="text-2xl font-bold text-gray-900">{value}</h4>
        )}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <p className="text-xs text-gray-500">{detail}</p>
        <button className="h-6 w-6 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50 transition-colors">
           <ChevronRight className="h-3.5 w-3.5 text-gray-600" />
        </button>
      </div>
    </div>
  );
}
