/**
 * One live transition stream per signed-in shell, fanned out to the screens.
 *
 * <TransitionsProvider> opens the stream on mount and aborts it on unmount;
 * useTransitions(handler) registers a screen's handler for as long as the
 * screen is mounted. Without a provider the hook does nothing, so a screen
 * rendered on its own (e.g. in a test) never opens a stream.
 */
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { openTransitionStream, type TransitionEvent } from "./events";

type Listener = (event: TransitionEvent) => void;

interface TransitionHub {
  subscribe(listener: Listener): () => void;
}

const TransitionsContext = createContext<TransitionHub | null>(null);

export function TransitionsProvider({ children }: { children: ReactNode }) {
  const [hub] = useState(() => {
    const listeners = new Set<Listener>();
    return {
      listeners,
      subscribe(listener: Listener) {
        listeners.add(listener);
        return () => {
          listeners.delete(listener);
        };
      },
    };
  });

  useEffect(
    () =>
      openTransitionStream({
        onTransition: (event) => {
          for (const listener of [...hub.listeners]) {
            try {
              listener(event);
            } catch {
              // One screen's handler must not tear down the shared stream.
            }
          }
        },
      }),
    [hub],
  );

  return <TransitionsContext.Provider value={hub}>{children}</TransitionsContext.Provider>;
}

/** Call `handler` for every transition while the calling component is mounted. */
export function useTransitions(handler: Listener): void {
  const hub = useContext(TransitionsContext);
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });
  useEffect(() => hub?.subscribe((event) => handlerRef.current(event)), [hub]);
}
