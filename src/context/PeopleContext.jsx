import { createContext, useCallback, useContext, useState } from 'react'
import PersonPanel from '../components/people/PersonPanel'

// Lets any clickable name in the app open the profile side panel without
// leaving the page. `openPerson` takes the small "card" the article people
// endpoint returns (id, name, headline, photo) so the panel can show the
// header instantly while the full profile loads.
const PeopleContext = createContext({ openPerson: () => {}, closePerson: () => {} })

export function PeopleProvider({ children }) {
  const [card, setCard] = useState(null)

  const openPerson = useCallback((person) => setCard(person), [])
  const closePerson = useCallback(() => setCard(null), [])

  return (
    <PeopleContext.Provider value={{ openPerson, closePerson, openId: card?.id ?? null }}>
      {children}
      {card && <PersonPanel card={card} onClose={closePerson} />}
    </PeopleContext.Provider>
  )
}

export function usePeople() {
  return useContext(PeopleContext)
}
