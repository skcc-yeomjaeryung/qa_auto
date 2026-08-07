import axios from "axios";
import { useMutation, useQuery } from "@tanstack/react-query";

export async function viaFetch() {
  return fetch("/api/customers/search", { method: "POST" });
}

export async function viaAxios() {
  return axios.post("/api/customers/search", { customerId: "CUS-1001" });
}

export function useCustomerQuery() {
  return useQuery({ queryKey: ["c"], queryFn: viaFetch });
}

export function useCustomerMutation() {
  return useMutation({ mutationFn: viaAxios });
}
