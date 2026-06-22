import { SaleTransaction, MenuItem, WasteRecord, Location, PaymentMethod, WasteReason, CountryMetrics } from "../types/models";

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

//CALCULATE DAILY REVENUE
export function calculateDailyRevenue(sales: SaleTransaction[], date: Date, currency: "USD" | "COP"): number {
  const daySales = sales.filter((sale) => sale.timestamp.toDateString() === date.toDateString());
  const total = daySales.reduce((sum, sale) => sum + sale.totalPrice[currency], 0);
  return Math.round(total * 100) / 100;
}

//CALCULATE LOCATION MARGIN
export function calculateLocationMargin(sales: SaleTransaction[], menuItems: MenuItem[], locationId: string, currency: "USD" | "COP"): number {
  const locationSales = sales.filter((sale) => sale.locationId === locationId);

  let totalRevenue = 0;
  let totalCost = 0;

  for (const sale of locationSales) {
    const item = menuItems.find((menuItem) => menuItem.id === sale.itemId);
    if (item === undefined) {
      continue;
    }
    totalRevenue += sale.totalPrice[currency];
    totalCost += item.ingredientCost[currency] * sale.quantity;
  }

  if (totalRevenue === 0) {
    return 0;
  }

  const margin = ((totalRevenue - totalCost) / totalRevenue) * 100;
  return Math.round(margin * 100) / 100;
}

//SCORE LOCATION PERFORMANCE
export function scoreLocationPerformance(
  location: Location,
  sales: SaleTransaction[],
  wasteRecords: WasteRecord[],
  menuItems: MenuItem[]
): number {
  const locationSales = sales.filter((sale) => sale.locationId === location.id);

  // --- Block 1: Revenue performance (max 40) ---
  const totalRevenue = locationSales.reduce((sum, sale) => sum + sale.totalPrice.USD, 0);
  const currentYear = new Date().getFullYear();
  const yearsOpen = Math.max(currentYear - location.openingYear, 1);
  const operatingDays = yearsOpen * 365;
  const avgDailyRevenue = totalRevenue / operatingDays;
  const revenueScore = Math.min((avgDailyRevenue / 1000) * 40, 40);

  // --- Block 2: Efficiency (max 30) ---
  const efficiencyScore = Math.min((locationSales.length / location.seatingCapacity) * 30, 30);

  // --- Block 3: Waste control (max 20) ---
  const totalWasteCost = calculateWasteCost(wasteRecords, location.id, "USD");
  const wastePercentage = totalRevenue === 0 ? 0 : (totalWasteCost / totalRevenue) * 100;
  const wasteScore = Math.max(20 - wastePercentage * 2, 0);

  // --- Block 4: Profit margin (max 10) ---
  const margin = calculateLocationMargin(sales, menuItems, location.id, "USD");
  const marginScore = Math.min(margin / 10, 10);

  const totalScore = revenueScore + efficiencyScore + wasteScore + marginScore;
  return Math.round(totalScore * 100) / 100;
}

//RANK LOCATIONS BY PERFORMANCE
export function rankLocationsByPerformance(
  locations: Location[],
  sales: SaleTransaction[],
  wasteRecords: WasteRecord[],
  menuItems: MenuItem[]
): Array<{ location: Location; score: number }> {
  const scored = locations.map((location) => ({
    location: location,
    score: scoreLocationPerformance(location, sales, wasteRecords, menuItems),
  }));

  return scored.sort((a, b) => b.score - a.score);
}

//COUNT SALES BY PAYMENT METHOD
export function countSalesByPaymentMethod(sales: SaleTransaction[]): Record<PaymentMethod, number> {
  const counts: Record<PaymentMethod, number> = {
    "Cash": 0,
    "Credit card": 0,
    "Debit card": 0,
    "Digital wallet": 0,
  };

  for (const sale of sales) {
    counts[sale.paymentMethod] += 1;
  }

  return counts;
}

//CALCULATE AVERAGE TICKET
export function calculateAverageTicket(sales: SaleTransaction[], currency: "USD" | "COP"): number {
  if (sales.length === 0) {
    return 0;
  }
  const total = sales.reduce((sum, sale) => sum + sale.totalPrice[currency], 0);
  return Math.round((total / sales.length) * 100) / 100;
}

//FIND TOP SELLING ITEMS
export function findTopSellingItems(
  sales: SaleTransaction[],
  menuItems: MenuItem[],
  topN: number
): Array<{ item: MenuItem; totalSold: number }> {
  const itemsWithTotals = menuItems.map((item) => {
    const totalSold = sales
      .filter((sale) => sale.itemId === item.id)
      .reduce((sum, sale) => sum + sale.quantity, 0);
    return { item: item, totalSold: totalSold };
  });

  const sorted = itemsWithTotals.sort((a, b) => b.totalSold - a.totalSold);
  return sorted.slice(0, topN);
}

//GROUP WASTE BY REASON
export function groupWasteByReason(wasteRecords: WasteRecord[]): Record<WasteReason, WasteRecord[]> {
  const groups: Record<WasteReason, WasteRecord[]> = {
    "Expired": [],
    "Cooking error": [],
    "Customer return": [],
    "Damage": [],
    "Other": [],
  };

  for (const record of wasteRecords) {
    groups[record.reason].push(record);
  }

  return groups;
}

//CALCULATE COUNTRY COMPARISON
export function calculateCountryComparison(
  sales: SaleTransaction[],
  locations: Location[],
  menuItems: MenuItem[]
): { Colombia: CountryMetrics; USA: CountryMetrics } {
  return {
    Colombia: buildCountryMetrics("Colombia", sales, locations),
    USA: buildCountryMetrics("USA", sales, locations),
  };
}

function buildCountryMetrics(
  country: "Colombia" | "USA",
  sales: SaleTransaction[],
  locations: Location[]
): CountryMetrics {
  const countryLocations = locations.filter((location) => location.country === country);
  const locationIds = countryLocations.map((location) => location.id);
  const countrySales = sales.filter((sale) => locationIds.includes(sale.locationId));

  const totalRevenue = {
    USD: countrySales.reduce((sum, sale) => sum + sale.totalPrice.USD, 0),
    COP: countrySales.reduce((sum, sale) => sum + sale.totalPrice.COP, 0),
  };

  const totalLocations = countryLocations.length;
  const totalSales = countrySales.length;

  const averageRevenuePerLocation = {
    USD: totalLocations === 0 ? 0 : Math.round((totalRevenue.USD / totalLocations) * 100) / 100,
    COP: totalLocations === 0 ? 0 : Math.round((totalRevenue.COP / totalLocations) * 100) / 100,
  };

  return {
    totalLocations: totalLocations,
    totalRevenue: {
      USD: Math.round(totalRevenue.USD * 100) / 100,
      COP: Math.round(totalRevenue.COP * 100) / 100,
    },
    averageRevenuePerLocation: averageRevenuePerLocation,
    totalSales: totalSales,
  };
}
