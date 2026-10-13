import { useNavigate } from "react-router";
import { NotFound } from "../components/NotFound";
import { Button } from "../ui/Button";

/** Full-page not found for paths outside any shell; deliberately generic. */
export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
      <NotFound />
      <Button variant="outline" className="self-start" onClick={() => navigate("/")}>
        Back to home
      </Button>
    </main>
  );
}