"use client";
import { Suspense } from "react";
import { Requests } from "@/components/command/requests";

// Home = Requests. Deep link to a selected request: /command?s=<session id>.
export default function RequestsPage() {
  // useSearchParams needs a Suspense boundary for the static build.
  return (
    <Suspense>
      <Requests />
    </Suspense>
  );
}
