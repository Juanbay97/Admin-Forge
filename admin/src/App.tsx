import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RouterProvider } from "react-router";
import { Providers } from "./shell/Providers";
import { createAppRouter } from "./shell/router";

export function App() {
  // Subscribing here re-renders the whole tree when the language changes, including code that reads copy through `t` without a hook.
  useTranslation();
  // Created inside the component so importing this module (the kit gallery build) never starts routing.
  const [router] = useState(createAppRouter);
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}