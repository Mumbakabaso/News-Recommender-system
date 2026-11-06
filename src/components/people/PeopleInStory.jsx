import { Users } from 'lucide-react'
import { usePeople } from '../../context/PeopleContext'
import { Avatar } from './ProfileBody'

// "People in this story": a row of chips under the headline, so readers
// can open a profile even for someone named only deep in the story.
export default function PeopleInStory({ people }) {
  const { openPerson } = usePeople()
  if (!people?.length) return null
  return (
    <div className="mb-6">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
        <Users className="w-3.5 h-3.5" /> People in this story
      </div>
      <div className="flex flex-wrap gap-2">
        {people.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => openPerson(p)}
            className="flex items-center gap-2 pl-1 pr-3 py-1 rounded-full bg-white border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50 text-left transition max-w-full"
            title={p.headline_position || p.short_description || p.name}
          >
            <Avatar person={p} size="sm" />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-slate-800 leading-tight truncate">{p.name}</span>
              {(p.headline_position || p.short_description) && (
                <span className="block text-[11px] text-slate-500 leading-tight truncate max-w-[14rem]">
                  {p.headline_position || p.short_description}
                </span>
              )}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
