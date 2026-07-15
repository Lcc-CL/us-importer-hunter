import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">
        US Importer Hunter
      </h1>
      <p className="max-w-md text-balance text-muted-foreground">
        AI-powered sales intelligence for freight forwarders. Discover, analyze
        and prioritize US importers.
      </p>
      <Button
        render={
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" />
        }
      >
        API Docs
      </Button>
    </main>
  );
}
