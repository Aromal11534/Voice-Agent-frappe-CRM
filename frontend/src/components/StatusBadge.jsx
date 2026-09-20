export default function StatusBadge({ value }) {
  if (!value) return null;
  const normalized = value.toLowerCase();
  
  let colorClass = 'bg-gray-100 text-gray-700';
  if (normalized.includes('hot')) colorClass = 'bg-black text-white';
  else if (normalized.includes('warm')) colorClass = 'bg-gray-800 text-gray-100';
  else if (normalized.includes('cold')) colorClass = 'bg-gray-200 text-gray-800';
  
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${colorClass}`}>
      {value}
    </span>
  );
}
