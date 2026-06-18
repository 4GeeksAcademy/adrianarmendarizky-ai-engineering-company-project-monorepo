import { SaleTransaction, MenuItem, WasteRecord } from "../types/models";

//CONVERT CURRENCY
export function convertCurrency(amount: number, fromCurrency: "USD" | "COP", toCurrency: "USD" | "COP"): number {
  if (fromCurrency === toCurrency) {
    return amount;
  }
  if (fromCurrency === "USD" && toCurrency === "COP") {
    return Math.round(amount * 4000 * 100) / 100;
  }
  return Math.round((amount / 4000) * 100) / 100;
}

//CALCULATE WASTE COST
export function calculateWasteCost(wasteRecords: WasteRecord[], locationId: string, currency: "USD" | "COP"): number {
  const locationWaste = wasteRecords.filter((record) => record.locationId === locationId);
  const total = locationWaste.reduce((sum, record) => sum + record.cost[currency], 0);
  return Math.round(total * 100) / 100;
}

