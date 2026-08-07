const handlers: Record<string, () => void> = {
  a: () => undefined,
};

export function Dyn({ name }: { name: string }) {
  return (
    <button
      onClick={() => {
        handlers[name]();
      }}
    >
      Run
    </button>
  );
}
