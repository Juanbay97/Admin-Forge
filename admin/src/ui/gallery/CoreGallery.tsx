import { Users } from "lucide-react";
import { z } from "zod";
import { Alert } from "../Alert";
import { Badge } from "../Badge";
import { Button } from "../Button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "../Card";
import { Checkbox, Radio, RadioGroup, Switch } from "../Choice";
import { EmptyState } from "../EmptyState";
import { Field } from "../Field";
import { useZodForm } from "../form";
import { FormError } from "../FormError";
import { Input, Textarea } from "../Input";
import { Select } from "../Select";
import { Separator } from "../Separator";
import { Skeleton, SkeletonText } from "../Skeleton";
import { Spinner } from "../Spinner";

const schema = z.object({ email: z.string().email("Enter a valid email address") });

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <h2 className="font-title text-section font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** Test-build gallery of the core kit: every variant and state the specs drive. */
export function CoreGallery() {
  const form = useZodForm(schema, { defaultValues: { email: "" } });
  const emailError = form.formState.errors.email?.message;
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 bg-app p-6 font-body text-body text-fg">
      <h1 className="font-title text-page font-bold">Kit core</h1>
      <p className="text-body">Plain body copy sits on a 14/20 scale.</p>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Default</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link action</Button>
          <Button disabled>Disabled</Button>
          <Button loading>Saving</Button>
          <Button asChild variant="outline">
            <a href="#docs">Docs link</a>
          </Button>
          <Spinner label="Syncing" />
        </div>
      </Section>

      <Section title="Form">
        <form noValidate className="flex max-w-md flex-col gap-4" onSubmit={form.handleSubmit(() => undefined)}>
          <Field label="Work email" hint="We send the invitation here." error={emailError} required>
            {(control) => <Input type="email" {...control} {...form.register("email")} />}
          </Field>
          <Field label="Department">
            {(control) => (
              <Select {...control} defaultValue="legal">
                <option value="legal">Legal</option>
                <option value="finance">Finance</option>
              </Select>
            )}
          </Field>
          <Field label="Notes">{(control) => <Textarea {...control} />}</Field>
          <Switch label="Notifications" />
          <Checkbox label="Accept terms" />
          <RadioGroup aria-label="Cadence" defaultValue="weekly">
            <Radio value="weekly" label="Weekly" />
            <Radio value="monthly" label="Monthly" />
          </RadioGroup>
          <FormError message="That email is already invited." />
        </form>
      </Section>

      <Section title="Surfaces">
        <Card>
          <CardHeader>
            <CardTitle>Usage this month</CardTitle>
            <CardDescription>Tokens routed through the gateway.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Badge tone="success">Active</Badge>
            <Badge tone="warning">Pending</Badge>
            <Badge tone="destructive">Suspended</Badge>
            <Badge tone="info">Admin</Badge>
            <Badge>Member</Badge>
          </CardContent>
          <CardFooter>
            <Button size="sm" variant="outline">Export</Button>
          </CardFooter>
        </Card>
        <Separator />
      </Section>

      <Section title="States">
        <div role="status" aria-label="Loading members" className="flex flex-col gap-3 rounded-card border border-line bg-surface p-5">
          <Skeleton className="h-6 w-1/3" />
          <SkeletonText lines={3} />
        </div>
        <EmptyState
          icon={Users}
          title="No members yet"
          hint="Invite the people who should use Forge in your company."
          action={<Button>Invite member</Button>}
        />
        <Alert tone="destructive" title="Could not load usage" action={<Button size="sm" variant="outline">Try again</Button>}>
          The request failed. Try again.
        </Alert>
        <Alert tone="info" title="Heads up">Informational messages are announced politely.</Alert>
      </Section>
    </main>
  );
}