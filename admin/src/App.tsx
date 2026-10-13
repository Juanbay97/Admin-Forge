import { useState } from "react";
import { RouterProvider } from "react-router";
import { Providers } from "./shell/Providers";
import { createAppRouter } from "./shell/router";

export function App() {
  // Created inside the component so importing this module (the kit gallery build) never starts routing.
  const [router] = useState(createAppRouter);
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}