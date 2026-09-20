export function formatDuration(seconds = 0) { 
  const total = Number(seconds) || 0; 
  return total >= 60 ? `${Math.floor(total / 60)}m ${Math.round(total % 60)}s` : `${Math.round(total)}s`; 
}

export function formatDate(value) { 
  if (!value) return 'Time unavailable'; 
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)); 
}

export function initials(name) { 
  return name ? name.split(' ').slice(0, 2).map((part) => part[0]).join('').toUpperCase() : 'UC'; 
}
