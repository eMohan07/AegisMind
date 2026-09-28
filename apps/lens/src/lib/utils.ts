import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format an ISO timestamp string or Date object into a readable date and 12-hour time format.
 * Example output: "Sep 28, 2026, 5:54 PM"
 */
export function format12HrDateTime(timestamp: string | Date | undefined | null): string {
  if (!timestamp) return "";
  if (typeof timestamp === "string" && (timestamp === "Just now" || timestamp.trim() === "")) {
    return timestamp;
  }
  const date = typeof timestamp === "string" ? new Date(timestamp) : timestamp;
  if (isNaN(date.getTime())) {
    return String(timestamp);
  }
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}
