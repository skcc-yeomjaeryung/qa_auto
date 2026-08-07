import { Button } from "./Button";

export function Page() {
  function onSearch() {
    fetch("/api/customers/search", { method: "POST" });
  }
  return <Button onClick={onSearch}>Search</Button>;
}
