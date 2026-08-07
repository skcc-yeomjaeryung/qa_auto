import { useRouter } from "next/router";

export default function Search() {
  const router = useRouter();
  return (
    <button
      onClick={() => {
        router.push("/customers/detail");
      }}
    >
      Go
    </button>
  );
}
