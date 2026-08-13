"use client";

import { useRouter } from "next/navigation";
import { clearToken } from "@/lib/auth";

export default function LogoutButton() {
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <button onClick={handleLogout} className="text-sm text-stone-300 hover:text-white">
      Log out
    </button>
  );
}