import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { checkBackendHealth, getSetupStatus } from "@/lib/api"

type SetupState = "loading" | "needs" | "done"

interface SetupContextType {
  setupState: SetupState
  markSetupDone: () => void
}

const SetupContext = createContext<SetupContextType | undefined>(undefined)

export function SetupProvider({ children }: { children: ReactNode }) {
  const [setupState, setSetupState] = useState<SetupState>("loading")

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      const health = await checkBackendHealth()
      if (cancelled) return
      if (!health.ok) {
        setSetupState("done")
        return
      }
      try {
        const { data } = await getSetupStatus()
        if (!cancelled) setSetupState(data.needs_setup ? "needs" : "done")
      } catch {
        if (!cancelled) setSetupState("done")
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const markSetupDone = () => setSetupState("done")

  return (
    <SetupContext.Provider value={{ setupState, markSetupDone }}>
      {children}
    </SetupContext.Provider>
  )
}

export function useSetup() {
  const context = useContext(SetupContext)
  if (!context) throw new Error("useSetup must be used within SetupProvider")
  return context
}
