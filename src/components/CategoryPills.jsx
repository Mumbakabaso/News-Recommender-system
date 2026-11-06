const FALLBACK = ['politics', 'economics', 'technology', 'global-affairs', 'sports', 'health']

export default function CategoryPills({ categories, active, onSelect }) {
  const list = categories?.length ? categories : FALLBACK
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onSelect(null)}
        className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
          !active ? 'bg-slate-900 text-white border-slate-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
        }`}
      >
        All
      </button>
      {list.map((c) => {
        const key = c.slug || c
        const label = c.name || c
        return (
          <button
            key={key}
            onClick={() => onSelect(key)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border capitalize transition-colors ${
              active === key ? 'bg-slate-900 text-white border-slate-900' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {label.replace('-', ' ')}
          </button>
        )
      })}
    </div>
  )
}
