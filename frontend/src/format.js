export const CATEGORIES = [
  "bag",
  "electronics",
  "wallet",
  "keys",
  "id_card",
  "clothing",
  "jewelry",
  "bottle",
  "umbrella",
  "book",
  "other",
];

const CATEGORY_LABELS = {
  bag: "Bag",
  electronics: "Electronics",
  wallet: "Wallet",
  keys: "Keys",
  id_card: "ID card",
  clothing: "Clothing",
  jewelry: "Jewelry",
  bottle: "Bottle",
  umbrella: "Umbrella",
  book: "Book",
  other: "Other",
};

const ATTRIBUTE_LABELS = {
  category: "Category",
  color: "Color",
  location: "Location",
  time: "Time",
  features: "Features",
  other: "Other",
};

export const PRIVATE_PLACEHOLDER = "[private detail withheld]";

export function categoryLabel(value) {
  if (!value) return null;
  return CATEGORY_LABELS[value] ?? value;
}

export function attributeLabel(value) {
  return ATTRIBUTE_LABELS[value] ?? value;
}

export function formatDateTime(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function orDash(value) {
  return value == null || value === "" ? "—" : value;
}

export function localInputToIso(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function maxLocalInput() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}
