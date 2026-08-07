import { SEARCH } from "@/lib/api";

export function Home() {
  return (
    <button
      onClick={() => {
        fetch(SEARCH, { method: "POST" });
      }}
    >
      Go
    </button>
  );
}
