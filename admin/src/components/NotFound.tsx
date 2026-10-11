// Deliberately generic: it must not reveal whether an organisation exists.
export function NotFound() {
  return (
    <section className="flex flex-col gap-2">
      <h1 className="font-title text-2xl font-bold text-primary">Not found</h1>
      <p>The page you requested could not be found.</p>
    </section>
  );
}