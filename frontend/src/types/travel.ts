export type TravelModePreference =
  | "mixed"
  | "flight"
  | "train"
  | "bus"
  | "car"
  | "train_bus"
  | "bus_car"
  | "flight_car"
  | "flight_train"
  | string;

export interface TravelSlots {
  origin?: string;
  destination?: string;
  travel_date?: string;
  budget?: number;
  mode_preference?: TravelModePreference;
  adults?: number;
  children?: number;
  car_type?: "hatchback" | "sedan" | "suv" | "ev";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface FlightLeg {
  from: string;
  to: string;
  departure?: string;
  arrival?: string;
  carrier?: string;
  flight_number?: string;
}

export interface Flight {
  id?: string;
  price_total?: string | number;
  currency?: string;
  duration?: string;
  stops?: number;
  segments?: FlightLeg[];
  source?: string;
  bookable?: boolean;
}

export interface Hotel {
  hotel_name?: string;
  city?: string;
  stars?: number;
  price_per_night?: string | number;
  currency?: string;
  check_in?: string;
  check_out?: string;
  source?: string;
  bookable?: boolean;
}

export interface BudgetHotel {
  name?: string;
  price_starting_from?: string | number;
  currency?: string;
  rating?: number;
  source?: string;
  source_url?: string;
  disclaimer?: string;
  bookable?: boolean;
}

export interface DailyCost {
  transport?: number;
  hotel?: number;
  food_estimate?: number;
  total?: number;
}

export interface RouteLeg {
  mode: "flight" | "hotel" | "budget_hotel" | "car" | "train" | "bus";
  from?: string;
  to?: string;
  name?: string;
  city?: string;
  departure?: string;
  cost?: string | number;
  price_per_night?: string | number;
  price_starting_from?: string | number;
  currency?: string;
  bookable?: boolean;
  source?: string;
  source_url?: string;
  disclaimer?: string;
  ai_score?: number;
  recommended?: boolean;
  recommendation_tag?: string;
}

export interface WeatherForecast {
  time?: string;
  temp_c?: number;
  feels_like?: number;
  description?: string;
  humidity?: number;
  wind_kph?: number;
}

export interface Weather {
  city?: string;
  forecasts?: WeatherForecast[];
}

export interface Roadmap {
  origin?: string;
  destination?: string;
  travel_date?: string;
  budget?: number;
  legs?: RouteLeg[];
  daily_cost?: Record<string, DailyCost>;
  total_estimate?: number;
  over_budget?: boolean;
  weather?: Weather;
  all_flights?: Flight[];
  all_hotels?: Hotel[];
  budget_hotels?: BudgetHotel[];
  passengers?: {
    adults: number;
    children: number;
    total: number;
    rooms_needed?: number;
  };
  car_cost?: any;
  train_fares?: any;
  bus_fares?: any;
  mode_preference?: TravelModePreference;
}

export interface PriceSignal {
  signal?: "book_now" | "wait" | "neutral" | "unknown";
  confidence?: number;
  note?: string;
  disclaimer?: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  roadmap?: Roadmap;
  price_signal?: PriceSignal;
  clarification_needed?: boolean;
}
