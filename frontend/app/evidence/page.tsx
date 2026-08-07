import { redirect } from "next/navigation";

export default function EvidencePage() {
  redirect("/runs?view=evidence");
}
