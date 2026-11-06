import { Globe2, MapPin, Layers } from 'lucide-react'

const OPTIONS = [
  { value: null, label: 'All news', Icon: Layers },
  { value: 'international', label: 'International', Icon: Globe2 },
  { value: 'zambia', label: 'Zambia', Icon: MapPin },
]

export default function RegionToggle({ value, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5" role="group" aria-label="News region">
      {OPTIONS.map(({ value: v, label, Icon }) => {
        const active = value === v
        return (
          <button
            key={label}
            type="button"
            onClick={() => onChange(v)}
            aria-pressed={active}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        )
      })}
    </div>
  )
}
