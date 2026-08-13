"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { hasValidToken } from "@/lib/auth";

// Wraps every route under app/(protected)/ -- the dashboard, suppliers,
// and account pages. (protected) is a route group: the parentheses mean
// it never shows up in the URL (still just "/" and "/suppliers"), it's
// only a way to give these three pages one shared layout/check instead
// of repeating it in each page. /login and /register live outside this
// group entirely, so they're never subject to it.
//
// This has to be a Client Component ("use client") because localStorage
// only exists in the browser -- a Server Component (the default for
// everything under app/) has no access to it at all.
export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!hasValidToken()) {
      router.replace("/login");
      return;
    }
    setChecking(false);
  }, [router]);

  if (checking) return null;

  return <>{children}</>;
}