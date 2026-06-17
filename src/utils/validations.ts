import { MenuItem, SaleTransaction, Location } from "../types/models";

export function validateMenuItem(item: MenuItem): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (item.basePrice.USD <= 0 || item.basePrice.COP <= 0) {
    errors.push("basePrice in both USD and COP must be greater than 0");
  }
  if (item.prepTimeMinutes <= 0 || item.prepTimeMinutes > 60) {
    errors.push("prepTimeMinutes must be between 1 and 60");
  }
  if (item.name.trim() === "") {
    errors.push("name must not be empty");
  }
  if (!item.isAvailableInColombia && !item.isAvailableInUSA) {
    errors.push("item must be available in at least one country");
  }

  return { valid: errors.length === 0, errors };
}

export function validateSaleTransaction(transaction: SaleTransaction): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (transaction.totalPrice.USD <= 0 || transaction.totalPrice.COP <= 0) {
    errors.push("totalPrice in both USD and COP must be greater than 0");
  }
  if (transaction.quantity <= 0) {
    errors.push("quantity must be greater than 0");
  }
  if (transaction.waiterName.trim() === "") {
    errors.push("waiterName must not be empty");
  }

  return { valid: errors.length === 0, errors };
}

export function validateLocation(location: Location): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (location.openingYear < 2008 || location.openingYear > new Date().getFullYear()) {
    errors.push("openingYear must be between 2008 and the current year");
  }
  if (location.monthlyRentCost.USD <= 0 || location.monthlyRentCost.COP <= 0) {
    errors.push("monthlyRentCost in both USD and COP must be greater than 0");
  }
  if (location.averageMonthlyUtilities.USD <= 0 || location.averageMonthlyUtilities.COP <= 0) {
    errors.push("averageMonthlyUtilities in both USD and COP must be greater than 0");
  }
  if (location.seatingCapacity <= 0) {
    errors.push("seatingCapacity must be greater than 0");
  }
  if (location.staffCount <= 0) {
    errors.push("staffCount must be greater than 0");
  }

  return { valid: errors.length === 0, errors };
}