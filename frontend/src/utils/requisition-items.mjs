export const REQUISITION_ITEMS = [
  "BI 1663 / DHA 1663",
  "Schedule B",
  "Coffin Type",
  "Cremation Fee",
  "Canvas",
  "Programs",
  "Flowers",
  "Candles",
  "Platters",
  "Grave Labor",
  "Other",
];
const manualLabels = {
  "Coffin Type": "Coffin type",
  Canvas: "Canvas type (e.g. A1)",
  Programs: "Company name",
  Other: "Other description",
};
export function paymentDetailLabel(category) {
  return manualLabels[category] || "Payment / supplier / service";
}
export function selectRequisitionItem(line, category) {
  return {
    ...line,
    category,
    description: manualLabels[category] ? "" : category,
  };
}
