import { useRouter } from "next/navigation";

export function NavButton() {
  const router = useRouter();
  return (
    <button
      onClick={() => {
        router.push("/customers/CUS-1001");
      }}
    >
      Open
    </button>
  );
}
