import { useForm } from "react-hook-form";
import { z } from "zod";

export const schema = z.string().min(1).regex(/^CUS-\d{4}$/);

export function RhfForm() {
  const { register, handleSubmit } = useForm();
  return (
    <form onSubmit={handleSubmit(() => undefined)}>
      <input {...register("customerId", { required: true, pattern: /^CUS-\d{4}$/ })} />
    </form>
  );
}
