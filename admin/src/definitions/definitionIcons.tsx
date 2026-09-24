/**
 * The shipped Lucide subset a definition's `icon` may name (ADMIN-SPEC §3.3).
 * Only these named imports are bundled — no CDN, no runtime fetch. The stored
 * value is the Lucide kebab-case name, so it stays meaningful to any surface.
 */
import {
  Apple,
  Backpack,
  Bath,
  Bed,
  Bike,
  BookOpen,
  Brush,
  BrushCleaning,
  Calendar,
  Cat,
  Clock,
  CookingPot,
  Dog,
  Droplets,
  Fish,
  Gamepad2,
  Heart,
  House,
  ListChecks,
  Moon,
  Music,
  Pencil,
  Recycle,
  Shirt,
  ShowerHead,
  Smile,
  Sofa,
  SprayCan,
  Sprout,
  Star,
  Sun,
  Toilet,
  Trash2,
  Utensils,
  Volleyball,
  WashingMachine,
  type LucideIcon,
} from "lucide-react";
import { TaskGlyph } from "./glyphs";

export interface DefinitionIconEntry {
  name: string;
  label: string;
  Icon: LucideIcon;
}

export const DEFINITION_ICONS: readonly DefinitionIconEntry[] = [
  { name: "bed", label: "Bed", Icon: Bed },
  { name: "bath", label: "Bath", Icon: Bath },
  { name: "shower-head", label: "Shower", Icon: ShowerHead },
  { name: "toilet", label: "Toilet", Icon: Toilet },
  { name: "brush", label: "Brush", Icon: Brush },
  { name: "smile", label: "Smile", Icon: Smile },
  { name: "shirt", label: "Clothes", Icon: Shirt },
  { name: "washing-machine", label: "Laundry", Icon: WashingMachine },
  { name: "utensils", label: "Meal", Icon: Utensils },
  { name: "cooking-pot", label: "Cooking", Icon: CookingPot },
  { name: "apple", label: "Snack", Icon: Apple },
  { name: "brush-cleaning", label: "Sweep", Icon: BrushCleaning },
  { name: "spray-can", label: "Clean", Icon: SprayCan },
  { name: "trash-2", label: "Bins", Icon: Trash2 },
  { name: "recycle", label: "Recycling", Icon: Recycle },
  { name: "sofa", label: "Tidy", Icon: Sofa },
  { name: "house", label: "Home", Icon: House },
  { name: "backpack", label: "School bag", Icon: Backpack },
  { name: "book-open", label: "Reading", Icon: BookOpen },
  { name: "pencil", label: "Homework", Icon: Pencil },
  { name: "music", label: "Music", Icon: Music },
  { name: "dog", label: "Dog", Icon: Dog },
  { name: "cat", label: "Cat", Icon: Cat },
  { name: "fish", label: "Fish", Icon: Fish },
  { name: "sprout", label: "Plants", Icon: Sprout },
  { name: "droplets", label: "Water", Icon: Droplets },
  { name: "bike", label: "Bike", Icon: Bike },
  { name: "volleyball", label: "Sport", Icon: Volleyball },
  { name: "gamepad-2", label: "Games", Icon: Gamepad2 },
  { name: "star", label: "Star", Icon: Star },
  { name: "heart", label: "Heart", Icon: Heart },
  { name: "sun", label: "Morning", Icon: Sun },
  { name: "moon", label: "Bedtime", Icon: Moon },
  { name: "clock", label: "Clock", Icon: Clock },
  { name: "calendar", label: "Calendar", Icon: Calendar },
  { name: "list-checks", label: "Checklist", Icon: ListChecks },
];

const BY_NAME = new Map(DEFINITION_ICONS.map((entry) => [entry.name, entry]));

export function findDefinitionIcon(name: string | null): DefinitionIconEntry | null {
  return name === null ? null : (BY_NAME.get(name) ?? null);
}

/** A definition's glyph; no icon, or one outside the subset, gets the generic task glyph. */
export function DefinitionIcon({ name, size = 17 }: { name: string | null; size?: number }) {
  const entry = findDefinitionIcon(name);
  if (!entry) return <TaskGlyph size={size} />;
  return <entry.Icon size={size} aria-hidden="true" focusable="false" data-icon={entry.name} />;
}
