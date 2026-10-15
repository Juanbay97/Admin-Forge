import { ForgotPassword } from "../public/ForgotPassword";
import { Join } from "../public/Join";
import { ResetPassword } from "../public/ResetPassword";
import { useServices } from "./services";

export const JoinRoute = () => <Join />;

export function ResetPasswordRoute() {
  const services = useServices();
  return <ResetPassword consume={(capability, password) => services.account.consumeReset(capability, password)} />;
}

export function ForgotPasswordRoute() {
  const services = useServices();
  return <ForgotPassword request={(email) => services.account.requestReset(email)} />;
}
