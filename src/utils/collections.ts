import { SaleTransaction, MenuItem, Location, MenuCategory } from "../types/models";

//FILTER: Sales by location
export function filterSalesByLocation(sales: SaleTransaction[], locationId: string): SaleTransaction[] {
  return sales.filter((sale) => sale.locationId === locationId);
}

//FILTER: Sales by date
export function filterSalesByDateRange(sales: SaleTransaction[], startDate: Date, endDate: Date): SaleTransaction[] {
  return sales.filter((sale) => sale.timestamp >= startDate && sale.timestamp <= endDate);
}

//FILTER: Sales by menu category
export function filterMenuItemsByCategory(items: MenuItem[], category: MenuCategory): MenuItem[] {
  return items.filter((item) => item.category === category);
}

//FILTER: Active Brasaland locations
export function filterActiveLocations(locations: Location[]): Location[] {
  return locations.filter((location) => location.status === "Active");
}

//SORT: Brasaland locations sorted by seating capacity
export function sortLocationsByCapacity(locations: Location[], order: "asc" | "desc"): Location[] {
  return [...locations].sort((a, b) =>
    order === "asc" ? a.seatingCapacity - b.seatingCapacity : b.seatingCapacity - a.seatingCapacity
  );
}

//SORT: Menu items sorted by price
export function sortMenuItemsByPrice(items: MenuItem[], currency: "USD" | "COP", order: "asc" | "desc"): MenuItem[] {
  return [...items].sort((a, b) =>
    order === "asc"
      ? a.basePrice[currency] - b.basePrice[currency]
      : b.basePrice[currency] - a.basePrice[currency]
  );
}