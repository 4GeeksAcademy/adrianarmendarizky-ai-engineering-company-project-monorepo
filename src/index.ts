import {
  sampleMenuItems,
  sampleLocations,
  sampleSales,
  WasteRecord,
} from "./types/models";
import {
  filterSalesByLocation,
  filterSalesByDateRange,
  filterMenuItemsByCategory,
  filterActiveLocations,
  sortLocationsByCapacity,
  sortMenuItemsByPrice,
} from "./utils/collections";
import {
  findLocationById,
  findMenuItemByName,
  binarySearchLocationByCapacity,
} from "./utils/search";
import {
  calculateDailyRevenue,
  calculateLocationMargin,
  calculateWasteCost,
  convertCurrency,
  scoreLocationPerformance,
  rankLocationsByPerformance,
  countSalesByPaymentMethod,
  calculateAverageTicket,
  findTopSellingItems,
  groupWasteByReason,
  calculateCountryComparison,
} from "./utils/transformations";
import {
  validateMenuItem,
  validateSaleTransaction,
  validateLocation,
} from "./utils/validations";

// --- A small WasteRecord sample, since the context didn't provide one ---
const sampleWaste: WasteRecord[] = [
  {
    id: "WASTE-001",
    locationId: "LOC-MEDELLIN-01",
    itemId: "ITEM-PICANHA-250",
    quantity: 1,
    reason: "Expired",
    cost: { USD: 7.2, COP: 28800 },
    timestamp: new Date("2024-03-15T22:00:00"),
    reportedBy: "Carlos Jiménez",
  },
  {
    id: "WASTE-002",
    locationId: "LOC-MEDELLIN-01",
    itemId: "ITEM-FRIES",
    quantity: 2,
    reason: "Cooking error",
    cost: { USD: 2.4, COP: 9600 },
    timestamp: new Date("2024-03-15T18:30:00"),
    reportedBy: "Carlos Jiménez",
  },
];

// ===================== COLLECTIONS =====================
console.log("========== COLLECTIONS ==========");

console.log("\n=== filterSalesByLocation (Medellín) ===");
console.log(filterSalesByLocation(sampleSales, "LOC-MEDELLIN-01").length, "sale(s)");

console.log("\n=== filterSalesByDateRange (Mar 1–31) ===");
console.log(
  filterSalesByDateRange(sampleSales, new Date("2024-03-01"), new Date("2024-03-31")).length,
  "sale(s)"
);

console.log("\n=== filterMenuItemsByCategory (Meat) ===");
console.log(filterMenuItemsByCategory(sampleMenuItems, "Meat").map((i) => i.name));

console.log("\n=== filterActiveLocations ===");
console.log(filterActiveLocations(sampleLocations).map((l) => l.name));

console.log("\n=== sortLocationsByCapacity (asc) ===");
console.log(sortLocationsByCapacity(sampleLocations, "asc").map((l) => l.seatingCapacity));

console.log("\n=== sortMenuItemsByPrice (USD, asc) ===");
console.log(sortMenuItemsByPrice(sampleMenuItems, "USD", "asc").map((i) => i.name));

// ===================== SEARCH =====================
console.log("\n========== SEARCH ==========");

console.log("\n=== findLocationById (LOC-MIAMI-01) ===");
console.log(findLocationById(sampleLocations, "LOC-MIAMI-01")?.name);

console.log("\n=== findMenuItemByName (case-insensitive) ===");
console.log(findMenuItemByName(sampleMenuItems, "picanha 250g")?.name);

console.log("\n=== binarySearchLocationByCapacity (target 100) ===");
const sortedByCapacity = sortLocationsByCapacity(sampleLocations, "asc");
console.log("index:", binarySearchLocationByCapacity(sortedByCapacity, 100));

// ===================== FINANCIAL =====================
console.log("\n========== FINANCIAL ==========");

console.log("\n=== convertCurrency ===");
console.log("100 USD to COP:", convertCurrency(100, "USD", "COP"));
console.log("400000 COP to USD:", convertCurrency(400000, "COP", "USD"));

console.log("\n=== calculateDailyRevenue (Mar 15, USD) ===");
console.log(calculateDailyRevenue(sampleSales, new Date("2024-03-15"), "USD"));

console.log("\n=== calculateLocationMargin (Medellín, USD) ===");
console.log(calculateLocationMargin(sampleSales, sampleMenuItems, "LOC-MEDELLIN-01", "USD"));

console.log("\n=== calculateWasteCost (Medellín, USD) ===");
console.log(calculateWasteCost(sampleWaste, "LOC-MEDELLIN-01", "USD"));

// ===================== SCORING =====================
console.log("\n========== SCORING ==========");

console.log("\n=== scoreLocationPerformance (Medellín) ===");
console.log(scoreLocationPerformance(sampleLocations[0], sampleSales, sampleWaste, sampleMenuItems));

console.log("\n=== rankLocationsByPerformance ===");
console.log(
  rankLocationsByPerformance(sampleLocations, sampleSales, sampleWaste, sampleMenuItems).map(
    (entry) => ({ name: entry.location.name, score: entry.score })
  )
);

// ===================== AGGREGATIONS =====================
console.log("\n========== AGGREGATIONS ==========");

console.log("\n=== countSalesByPaymentMethod ===");
console.log(countSalesByPaymentMethod(sampleSales));

console.log("\n=== calculateAverageTicket (USD) ===");
console.log(calculateAverageTicket(sampleSales, "USD"));

console.log("\n=== findTopSellingItems (top 2) ===");
console.log(
  findTopSellingItems(sampleSales, sampleMenuItems, 2).map((entry) => ({
    name: entry.item.name,
    totalSold: entry.totalSold,
  }))
);

console.log("\n=== groupWasteByReason ===");
const grouped = groupWasteByReason(sampleWaste);
console.log("Expired:", grouped["Expired"].length, "| Cooking error:", grouped["Cooking error"].length);

console.log("\n=== calculateCountryComparison ===");
console.log(JSON.stringify(calculateCountryComparison(sampleSales, sampleLocations, sampleMenuItems), null, 2));

// ===================== VALIDATIONS =====================
console.log("\n========== VALIDATIONS ==========");

console.log("\n=== validateMenuItem (valid) ===");
console.log(validateMenuItem(sampleMenuItems[0]));

console.log("\n=== validateSaleTransaction (valid) ===");
console.log(validateSaleTransaction(sampleSales[0]));

console.log("\n=== validateLocation (valid) ===");
console.log(validateLocation(sampleLocations[0]));