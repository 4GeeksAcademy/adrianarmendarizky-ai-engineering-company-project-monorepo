//MAIN INTERFACES AND TYPES

export interface MenuItem {
  id: string; // Menu item ID (e.g., "ITEM-PICANHA-250")
  name: string; // Item name (e.g., "Picanha 250g")
  category: MenuCategory; // Food category
  basePrice: Price; // Base price (can vary by location)
  ingredientCost: Price; // Cost of ingredients per unit
  prepTimeMinutes: number; // Average preparation time
  isAvailableInColombia: boolean;
  isAvailableInUSA: boolean;
  allergens: string[]; // List of allergens
  status: MenuItemStatus;
}

export interface Price {
  USD: number; // Price in US Dollars
  COP: number; // Price in Colombian Pesos
}

export type MenuCategory = "Meat" | "Side" | "Beverage" | "Dessert" | "Combo";
export type MenuItemStatus = "Active" | "Seasonal" | "Discontinued";

export interface SaleTransaction {
  id: string; // Transaction ID (e.g., "TXN-2024-15482")
  locationId: string; // Location where sale occurred
  itemId: string; // Menu item sold
  quantity: number; // Number of units sold
  totalPrice: Price; // Total price charged
  paymentMethod: PaymentMethod; // How customer paid
  timestamp: Date; // When the sale occurred
  waiterName: string; // Staff member who served
}

export type PaymentMethod = "Cash" | "Credit card" | "Debit card" | "Digital wallet";

export interface Location {
  id: string; // Location ID (e.g., "LOC-MEDELLIN-01")
  name: string; // Location name
  city: string; // City name
  country: Country; // Colombia or USA
  openingYear: number; // Year opened
  seatingCapacity: number; // Maximum number of customers
  staffCount: number; // Number of employees
  monthlyRentCost: Price; // Monthly rent
  averageMonthlyUtilities: Price; // Average monthly utilities
  manager: string; // Location manager name
  status: LocationStatus;
}

export type Country = "Colombia" | "USA";
export type LocationStatus = "Active" | "Temporarily closed" | "Under renovation";

export interface WasteRecord {
  id: string; // Waste record ID
  locationId: string; // Location where waste occurred
  itemId: string; // Menu item wasted
  quantity: number; // Number of units wasted
  reason: WasteReason; // Why it was wasted
  cost: Price; // Cost of wasted items
  timestamp: Date; // When it was recorded
  reportedBy: string; // Staff member who reported it
}

export type WasteReason =
  | "Expired"
  | "Cooking error"
  | "Customer return"
  | "Damage"
  | "Other";

export interface CountryMetrics {
  totalLocations: number;
  totalRevenue: Price;
  averageRevenuePerLocation: Price;
  totalSales: number;
}



//SAMPLE DATA

export const sampleMenuItems: MenuItem[] = [
  {
    id: "ITEM-PICANHA-250",
    name: "Picanha 250g",
    category: "Meat",
    basePrice: { USD: 18.5, COP: 74000 },
    ingredientCost: { USD: 7.2, COP: 28800 },
    prepTimeMinutes: 15,
    isAvailableInColombia: true,
    isAvailableInUSA: true,
    allergens: [],
    status: "Active",
  },
  {
    id: "ITEM-FRIES",
    name: "French Fries",
    category: "Side",
    basePrice: { USD: 4.5, COP: 18000 },
    ingredientCost: { USD: 1.2, COP: 4800 },
    prepTimeMinutes: 8,
    isAvailableInColombia: true,
    isAvailableInUSA: true,
    allergens: [],
    status: "Active",
  },
  {
    id: "ITEM-COKE",
    name: "Coca-Cola",
    category: "Beverage",
    basePrice: { USD: 2.5, COP: 10000 },
    ingredientCost: { USD: 0.8, COP: 3200 },
    prepTimeMinutes: 2,
    isAvailableInColombia: true,
    isAvailableInUSA: true,
    allergens: [],
    status: "Active",
  },
];


export const sampleLocations: Location[] = [
  {
    id: "LOC-MEDELLIN-01",
    name: "Brasaland Medellín Centro",
    city: "Medellín",
    country: "Colombia",
    openingYear: 2008,
    seatingCapacity: 80,
    staffCount: 12,
    monthlyRentCost: { USD: 1500, COP: 6000000 },
    averageMonthlyUtilities: { USD: 400, COP: 1600000 },
    manager: "Carlos Jiménez",
    status: "Active",
  },
  {
    id: "LOC-MIAMI-01",
    name: "Brasaland Miami Beach",
    city: "Miami",
    country: "USA",
    openingYear: 2018,
    seatingCapacity: 100,
    staffCount: 15,
    monthlyRentCost: { USD: 5500, COP: 22000000 },
    averageMonthlyUtilities: { USD: 800, COP: 3200000 },
    manager: "Jake Morrison",
    status: "Active",
  },
  // Sample data: 12 more locations so the chain reaches 14 (invented for demo purposes)
  { id: "LOC-MEDELLIN-02", name: "Brasaland Medellín El Poblado", city: "Medellín", country: "Colombia", openingYear: 2012, seatingCapacity: 90, staffCount: 14, monthlyRentCost: { USD: 1900, COP: 7600000 }, averageMonthlyUtilities: { USD: 450, COP: 1800000 }, manager: "Laura Henao", status: "Active" },
  { id: "LOC-MEDELLIN-03", name: "Brasaland Medellín Laureles", city: "Medellín", country: "Colombia", openingYear: 2015, seatingCapacity: 70, staffCount: 11, monthlyRentCost: { USD: 1100, COP: 4400000 }, averageMonthlyUtilities: { USD: 320, COP: 1280000 }, manager: "Andrés Ocampo", status: "Active" },
  { id: "LOC-ENVIGADO-01", name: "Brasaland Envigado", city: "Envigado", country: "Colombia", openingYear: 2016, seatingCapacity: 65, staffCount: 10, monthlyRentCost: { USD: 950, COP: 3800000 }, averageMonthlyUtilities: { USD: 290, COP: 1160000 }, manager: "Valentina Cárdenas", status: "Active" },
  { id: "LOC-BOGOTA-01", name: "Brasaland Bogotá Chapinero", city: "Bogotá", country: "Colombia", openingYear: 2014, seatingCapacity: 110, staffCount: 16, monthlyRentCost: { USD: 2200, COP: 8800000 }, averageMonthlyUtilities: { USD: 520, COP: 2080000 }, manager: "Sebastián Giraldo", status: "Active" },
  { id: "LOC-BOGOTA-02", name: "Brasaland Bogotá Usaquén", city: "Bogotá", country: "Colombia", openingYear: 2019, seatingCapacity: 85, staffCount: 13, monthlyRentCost: { USD: 1800, COP: 7200000 }, averageMonthlyUtilities: { USD: 430, COP: 1720000 }, manager: "Mónica Herrera", status: "Active" },
  { id: "LOC-CALI-01", name: "Brasaland Cali Granada", city: "Cali", country: "Colombia", openingYear: 2017, seatingCapacity: 75, staffCount: 12, monthlyRentCost: { USD: 1000, COP: 4000000 }, averageMonthlyUtilities: { USD: 310, COP: 1240000 }, manager: "Julián Salazar", status: "Active" },
  { id: "LOC-CARTAGENA-01", name: "Brasaland Cartagena Bocagrande", city: "Cartagena", country: "Colombia", openingYear: 2020, seatingCapacity: 95, staffCount: 14, monthlyRentCost: { USD: 2000, COP: 8000000 }, averageMonthlyUtilities: { USD: 480, COP: 1920000 }, manager: "Paula Mejía", status: "Under renovation" },
  { id: "LOC-MIAMI-02", name: "Brasaland Miami Brickell", city: "Miami", country: "USA", openingYear: 2019, seatingCapacity: 120, staffCount: 18, monthlyRentCost: { USD: 6800, COP: 27200000 }, averageMonthlyUtilities: { USD: 950, COP: 3800000 }, manager: "Rachel Bennett", status: "Active" },
  { id: "LOC-MIAMI-03", name: "Brasaland Miami Wynwood", city: "Miami", country: "USA", openingYear: 2021, seatingCapacity: 90, staffCount: 14, monthlyRentCost: { USD: 5200, COP: 20800000 }, averageMonthlyUtilities: { USD: 780, COP: 3120000 }, manager: "Marcus Hall", status: "Active" },
  { id: "LOC-CORALGABLES-01", name: "Brasaland Coral Gables", city: "Coral Gables", country: "USA", openingYear: 2020, seatingCapacity: 85, staffCount: 13, monthlyRentCost: { USD: 5000, COP: 20000000 }, averageMonthlyUtilities: { USD: 720, COP: 2880000 }, manager: "Olivia Reyes", status: "Active" },
  { id: "LOC-FTLAUDERDALE-01", name: "Brasaland Fort Lauderdale Las Olas", city: "Fort Lauderdale", country: "USA", openingYear: 2022, seatingCapacity: 100, staffCount: 15, monthlyRentCost: { USD: 5600, COP: 22400000 }, averageMonthlyUtilities: { USD: 810, COP: 3240000 }, manager: "Daniel Whitaker", status: "Temporarily closed" },
  { id: "LOC-ORLANDO-01", name: "Brasaland Orlando International Drive", city: "Orlando", country: "USA", openingYear: 2023, seatingCapacity: 130, staffCount: 19, monthlyRentCost: { USD: 6200, COP: 24800000 }, averageMonthlyUtilities: { USD: 900, COP: 3600000 }, manager: "Priya Shah", status: "Active" },
];

export const sampleSales: SaleTransaction[] = [
  {
    id: "TXN-2024-15482",
    locationId: "LOC-MEDELLIN-01",
    itemId: "ITEM-PICANHA-250",
    quantity: 2,
    totalPrice: { USD: 37.0, COP: 148000 },
    paymentMethod: "Credit card",
    timestamp: new Date("2024-03-15T19:30:00"),
    waiterName: "María González",
  },
  {
    id: "TXN-2024-15483",
    locationId: "LOC-MIAMI-01",
    itemId: "ITEM-FRIES",
    quantity: 3,
    totalPrice: { USD: 13.5, COP: 54000 },
    paymentMethod: "Cash",
    timestamp: new Date("2024-03-15T20:15:00"),
    waiterName: "John Smith",
  },
  // Sample data: more sales across the other locations (invented for demo purposes)
  { id: "TXN-2024-15455", locationId: "LOC-BOGOTA-02", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-01T14:00:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15456", locationId: "LOC-ORLANDO-01", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-01T21:20:00"), waiterName: "Sofia Martinez" },
  { id: "TXN-2024-15457", locationId: "LOC-MIAMI-02", itemId: "ITEM-FRIES", quantity: 1, totalPrice: { USD: 4.5, COP: 18000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-02T18:00:00"), waiterName: "Jordan Lee" },
  { id: "TXN-2024-15458", locationId: "LOC-MIAMI-02", itemId: "ITEM-PICANHA-250", quantity: 1, totalPrice: { USD: 18.5, COP: 74000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-04T17:30:00"), waiterName: "Sofia Martinez" },
  { id: "TXN-2024-15459", locationId: "LOC-CALI-01", itemId: "ITEM-FRIES", quantity: 1, totalPrice: { USD: 4.5, COP: 18000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-04T17:50:00"), waiterName: "Mateo Cano" },
  { id: "TXN-2024-15460", locationId: "LOC-BOGOTA-02", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-04T20:10:00"), waiterName: "Juan Pablo Torres" },
  { id: "TXN-2024-15461", locationId: "LOC-BOGOTA-02", itemId: "ITEM-COKE", quantity: 5, totalPrice: { USD: 12.5, COP: 50000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-06T15:35:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15462", locationId: "LOC-ORLANDO-01", itemId: "ITEM-COKE", quantity: 2, totalPrice: { USD: 5, COP: 20000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-06T16:50:00"), waiterName: "Grace Holloway" },
  { id: "TXN-2024-15463", locationId: "LOC-FTLAUDERDALE-01", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-07T18:10:00"), waiterName: "Ryan Foster" },
  { id: "TXN-2024-15464", locationId: "LOC-MEDELLIN-03", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-07T18:15:00"), waiterName: "Daniela Ríos" },
  { id: "TXN-2024-15465", locationId: "LOC-MIAMI-02", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-07T21:45:00"), waiterName: "Grace Holloway" },
  { id: "TXN-2024-15466", locationId: "LOC-MIAMI-03", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-08T17:15:00"), waiterName: "Ryan Foster" },
  { id: "TXN-2024-15467", locationId: "LOC-ENVIGADO-01", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-08T19:45:00"), waiterName: "Esteban Mora" },
  { id: "TXN-2024-15468", locationId: "LOC-ENVIGADO-01", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-09T18:45:00"), waiterName: "Juan Pablo Torres" },
  { id: "TXN-2024-15469", locationId: "LOC-CALI-01", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-09T19:50:00"), waiterName: "Mateo Cano" },
  { id: "TXN-2024-15470", locationId: "LOC-CORALGABLES-01", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-10T15:50:00"), waiterName: "Grace Holloway" },
  { id: "TXN-2024-15471", locationId: "LOC-MEDELLIN-02", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-10T15:55:00"), waiterName: "Isabela Ruiz" },
  { id: "TXN-2024-15472", locationId: "LOC-MIAMI-02", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-10T16:35:00"), waiterName: "Miguel Alvarez" },
  { id: "TXN-2024-15473", locationId: "LOC-CALI-01", itemId: "ITEM-COKE", quantity: 2, totalPrice: { USD: 5, COP: 20000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-10T18:15:00"), waiterName: "Juan Pablo Torres" },
  { id: "TXN-2024-15474", locationId: "LOC-CORALGABLES-01", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-10T20:10:00"), waiterName: "Nina Patel" },
  { id: "TXN-2024-15475", locationId: "LOC-MEDELLIN-03", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-11T17:15:00"), waiterName: "Natalia Pineda" },
  { id: "TXN-2024-15476", locationId: "LOC-ORLANDO-01", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-11T18:25:00"), waiterName: "Miguel Alvarez" },
  { id: "TXN-2024-15477", locationId: "LOC-MEDELLIN-02", itemId: "ITEM-FRIES", quantity: 4, totalPrice: { USD: 18, COP: 72000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-12T18:40:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15478", locationId: "LOC-MIAMI-03", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-13T20:45:00"), waiterName: "Ryan Foster" },
  { id: "TXN-2024-15479", locationId: "LOC-MIAMI-03", itemId: "ITEM-PICANHA-250", quantity: 3, totalPrice: { USD: 55.5, COP: 222000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-14T20:10:00"), waiterName: "Emily Carter" },
  { id: "TXN-2024-15480", locationId: "LOC-ORLANDO-01", itemId: "ITEM-COKE", quantity: 1, totalPrice: { USD: 2.5, COP: 10000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-15T13:05:00"), waiterName: "Hannah Cole" },
  { id: "TXN-2024-15481", locationId: "LOC-MEDELLIN-03", itemId: "ITEM-COKE", quantity: 2, totalPrice: { USD: 5, COP: 20000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-15T17:10:00"), waiterName: "Juan Pablo Torres" },
  { id: "TXN-2024-15484", locationId: "LOC-BOGOTA-01", itemId: "ITEM-PICANHA-250", quantity: 1, totalPrice: { USD: 18.5, COP: 74000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-17T14:15:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15485", locationId: "LOC-MEDELLIN-02", itemId: "ITEM-COKE", quantity: 3, totalPrice: { USD: 7.5, COP: 30000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-18T17:40:00"), waiterName: "Mateo Cano" },
  { id: "TXN-2024-15486", locationId: "LOC-ENVIGADO-01", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-19T13:05:00"), waiterName: "Daniela Ríos" },
  { id: "TXN-2024-15487", locationId: "LOC-BOGOTA-02", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-19T15:50:00"), waiterName: "Esteban Mora" },
  { id: "TXN-2024-15488", locationId: "LOC-BOGOTA-01", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-19T16:40:00"), waiterName: "Esteban Mora" },
  { id: "TXN-2024-15489", locationId: "LOC-BOGOTA-01", itemId: "ITEM-PICANHA-250", quantity: 1, totalPrice: { USD: 18.5, COP: 74000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-19T20:30:00"), waiterName: "Santiago Vélez" },
  { id: "TXN-2024-15490", locationId: "LOC-MEDELLIN-03", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-20T13:25:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15491", locationId: "LOC-BOGOTA-02", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-20T13:45:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15492", locationId: "LOC-MIAMI-03", itemId: "ITEM-FRIES", quantity: 4, totalPrice: { USD: 18, COP: 72000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-21T13:30:00"), waiterName: "Hannah Cole" },
  { id: "TXN-2024-15493", locationId: "LOC-MEDELLIN-02", itemId: "ITEM-COKE", quantity: 3, totalPrice: { USD: 7.5, COP: 30000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-21T18:35:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15494", locationId: "LOC-CALI-01", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-22T12:15:00"), waiterName: "Esteban Mora" },
  { id: "TXN-2024-15495", locationId: "LOC-BOGOTA-01", itemId: "ITEM-FRIES", quantity: 4, totalPrice: { USD: 18, COP: 72000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-22T18:15:00"), waiterName: "Isabela Ruiz" },
  { id: "TXN-2024-15496", locationId: "LOC-ENVIGADO-01", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-23T15:25:00"), waiterName: "Santiago Vélez" },
  { id: "TXN-2024-15497", locationId: "LOC-FTLAUDERDALE-01", itemId: "ITEM-FRIES", quantity: 1, totalPrice: { USD: 4.5, COP: 18000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-25T14:05:00"), waiterName: "Chris Dalton" },
  { id: "TXN-2024-15498", locationId: "LOC-FTLAUDERDALE-01", itemId: "ITEM-PICANHA-250", quantity: 1, totalPrice: { USD: 18.5, COP: 74000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-25T21:20:00"), waiterName: "Hannah Cole" },
  { id: "TXN-2024-15499", locationId: "LOC-CARTAGENA-01", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-26T12:30:00"), waiterName: "Daniela Ríos" },
  { id: "TXN-2024-15500", locationId: "LOC-BOGOTA-01", itemId: "ITEM-PICANHA-250", quantity: 2, totalPrice: { USD: 37, COP: 148000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-26T18:10:00"), waiterName: "Mateo Cano" },
  { id: "TXN-2024-15501", locationId: "LOC-ORLANDO-01", itemId: "ITEM-PICANHA-250", quantity: 4, totalPrice: { USD: 74, COP: 296000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-26T21:50:00"), waiterName: "Jordan Lee" },
  { id: "TXN-2024-15502", locationId: "LOC-CORALGABLES-01", itemId: "ITEM-PICANHA-250", quantity: 4, totalPrice: { USD: 74, COP: 296000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-27T15:20:00"), waiterName: "Nina Patel" },
  { id: "TXN-2024-15503", locationId: "LOC-MIAMI-03", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-27T15:40:00"), waiterName: "Hannah Cole" },
  { id: "TXN-2024-15504", locationId: "LOC-CARTAGENA-01", itemId: "ITEM-PICANHA-250", quantity: 1, totalPrice: { USD: 18.5, COP: 74000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-27T18:05:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15505", locationId: "LOC-ENVIGADO-01", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-28T14:50:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15506", locationId: "LOC-MEDELLIN-03", itemId: "ITEM-FRIES", quantity: 1, totalPrice: { USD: 4.5, COP: 18000 }, paymentMethod: "Debit card", timestamp: new Date("2024-03-28T16:40:00"), waiterName: "David Duque" },
  { id: "TXN-2024-15507", locationId: "LOC-CALI-01", itemId: "ITEM-FRIES", quantity: 4, totalPrice: { USD: 18, COP: 72000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-28T18:45:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15508", locationId: "LOC-CARTAGENA-01", itemId: "ITEM-FRIES", quantity: 5, totalPrice: { USD: 22.5, COP: 90000 }, paymentMethod: "Digital wallet", timestamp: new Date("2024-03-29T16:50:00"), waiterName: "Camila Arango" },
  { id: "TXN-2024-15509", locationId: "LOC-MEDELLIN-02", itemId: "ITEM-FRIES", quantity: 4, totalPrice: { USD: 18, COP: 72000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-30T14:40:00"), waiterName: "Natalia Pineda" },
  { id: "TXN-2024-15510", locationId: "LOC-CORALGABLES-01", itemId: "ITEM-FRIES", quantity: 3, totalPrice: { USD: 13.5, COP: 54000 }, paymentMethod: "Cash", timestamp: new Date("2024-03-31T15:35:00"), waiterName: "Nina Patel" },
  { id: "TXN-2024-15511", locationId: "LOC-CORALGABLES-01", itemId: "ITEM-FRIES", quantity: 2, totalPrice: { USD: 9, COP: 36000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-31T19:25:00"), waiterName: "Chris Dalton" },
  { id: "TXN-2024-15512", locationId: "LOC-MIAMI-02", itemId: "ITEM-COKE", quantity: 4, totalPrice: { USD: 10, COP: 40000 }, paymentMethod: "Credit card", timestamp: new Date("2024-03-31T19:45:00"), waiterName: "Sofia Martinez" },
];
