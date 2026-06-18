import { Location, MenuItem } from "../types/models";

//SEARCH: Locations by ID

export function findLocationById(locations: Location[], id: string): Location | null {
  return locations.find(location => location.id === id) ?? null;
}

//SEARCH: Menu items by Name
export function findMenuItemByName(items: MenuItem[], name: string): MenuItem | null {
  return items.find((item) => item.name.toLowerCase() === name.toLowerCase()) ?? null;
}

//SEARCH: Locations by Capacity
export function binarySearchLocationByCapacity(sortedLocations: Location[], targetCapacity: number): number {
  let low = 0;
  let high = sortedLocations.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const midCapacity = sortedLocations[mid].seatingCapacity;

    if (midCapacity === targetCapacity) {
      return mid;
    } else if (midCapacity < targetCapacity) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return -1;
}