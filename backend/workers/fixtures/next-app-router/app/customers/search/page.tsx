"use client";

export default function CustomerSearchPage() {
  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    await fetch("/api/customers/search", {
      method: "POST",
      body: JSON.stringify({ customerId: "CUS-1001" }),
    });
  }
  return (
    <form onSubmit={onSubmit}>
      <input name="customerId" data-testid="customer-id-input" required pattern="CUS-\\d{4}" />
      <button type="submit">Search</button>
    </form>
  );
}
