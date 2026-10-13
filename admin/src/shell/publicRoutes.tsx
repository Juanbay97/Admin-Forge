import { ResetPassword } from "../public/ResetPassword";
import { useServices } from "./services";

export function ResetPasswordRoute() {
  const services = useServices();
  return <ResetPassword consume={(capability, password) => services.account.consumeReset(capability, password)} />;
}
