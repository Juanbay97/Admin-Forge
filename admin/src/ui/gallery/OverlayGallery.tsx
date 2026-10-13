import { MoreHorizontal, Search, Users } from "lucide-react";
import { useState } from "react";
import { Button } from "../Button";
import { CopyButton } from "../CopyButton";
import { DataTable, type Column } from "../DataTable";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../DropdownMenu";
import { EmptyState } from "../EmptyState";
import { Field } from "../Field";
import { Input } from "../Input";
import { KeyField } from "../KeyField";
import { AlertDialog, Dialog, Sheet } from "../overlay/Dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../Tabs";
import { ToastProvider, useToast } from "../toast/Toast";
import { Tooltip } from "../Tooltip";

interface Person {
  name: string;
  tokens: number;
}

const PEOPLE: Person[] = [
  ["Alex", 120], ["Bea", 95], ["Cy", 80], ["Dee", 70], ["Eli", 60], ["Fay", 55],
  ["Gus", 50], ["Hal", 45], ["Ivy", 40], ["Jo", 35], ["Kim", 900], ["Lou", 5],
].map(([name, tokens]) => ({ name: name as string, tokens: tokens as number }));

const COLUMNS: Column<Person>[] = [
  { id: "name", header: "Name", cell: (person) => person.name, sortValue: (person) => person.name },
  { id: "tokens", header: "Tokens", cell: (person) => person.tokens, sortValue: (person) => person.tokens, align: "right" },
];

function Gallery() {
  const toast = useToast();
  const [dialog, setDialog] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [filter, setFilter] = useState("");
  const [key, setKey] = useState("");
  const [submitted, setSubmitted] = useState<number | null>(null);
  const rows = PEOPLE.filter((person) => person.name.toLowerCase().includes(filter.toLowerCase()));

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 bg-app p-6 font-body text-body text-fg">
      <h1 className="font-title text-page font-bold">Kit overlays and data</h1>

      <section aria-label="Overlays" className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setDialog(true)}>Open dialog</Button>
        <Button variant="outline" onClick={() => setSheet(true)}>Open sheet</Button>
        <Button variant="destructive" onClick={() => setConfirm(true)}>Delete workspace</Button>
        <Button variant="secondary" onClick={() => toast.push({ tone: "success", title: "Catalogue published", message: "3 models are live." })}>Show toast</Button>
        <span>Deleted: {deleted ? "yes" : "no"}</span>
      </section>

      <Dialog open={dialog} onOpenChange={setDialog} title="Rename workspace" description="Members see the new name immediately.">
        <Field label="Workspace name">{(control) => <Input defaultValue="Forge" {...control} />}</Field>
        <div className="flex justify-end gap-3">
          <Button variant="outline" onClick={() => setDialog(false)}>Cancel</Button>
          <Button onClick={() => setDialog(false)}>Save</Button>
        </div>
      </Dialog>
      <Sheet open={sheet} onOpenChange={setSheet} title="Filters" description="Narrow the list.">
        <Field label="Department">{(control) => <Input {...control} />}</Field>
      </Sheet>
      <AlertDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Delete workspace?"
        description="This removes every member's access."
        confirmLabel="Delete"
        destructive
        onConfirm={() => setDeleted(true)}
      />

      <section aria-label="Navigation" className="flex flex-col gap-4">
        <Tabs defaultValue="overview">
          <TabsList aria-label="Sections">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="usage">Usage</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">Overview panel</TabsContent>
          <TabsContent value="usage">Usage panel</TabsContent>
        </Tabs>
        <div className="flex items-center gap-3">
          <Tooltip content="Copies the value to the clipboard">
            <Button variant="outline">Copy help</Button>
          </Tooltip>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" aria-label="Row actions"><MoreHorizontal aria-hidden="true" className="size-4" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem>Rename</DropdownMenuItem>
              <DropdownMenuItem destructive>Remove</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </section>

      <section aria-label="Data" className="flex flex-col gap-6">
        <DataTable
          caption="People"
          columns={COLUMNS}
          rows={rows}
          rowKey={(person) => person.name}
          pageSize={5}
          filter={
            <Field label="Filter people">
              {(control) => (
                <span className="relative block">
                  <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
                  <Input className="pl-9" value={filter} onChange={(event) => setFilter(event.target.value)} {...control} />
                </span>
              )}
            </Field>
          }
          empty={<EmptyState icon={Users} title="Nobody matches" hint="Try a different name." />}
        />
        <DataTable caption="People" loading loadingLabel="Loading people" columns={COLUMNS} rows={[]} rowKey={(person) => person.name} empty={null} />

        <div className="flex items-center gap-3">
          <CopyButton value="https://forge.example/join/abc" label="Copy invite link" />
        </div>
        <form
          className="flex max-w-md flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(key.length);
            setKey("");
          }}
        >
          <KeyField label="API key" value={key} onValueChange={setKey} lastFour="4f2a" />
          <Button type="submit" className="self-start">Save key</Button>
          {submitted !== null && <p role="status">Submitted {submitted} characters</p>}
        </form>
      </section>
    </main>
  );
}

export function OverlayGallery() {
  return (
    <ToastProvider>
      <Gallery />
    </ToastProvider>
  );
}