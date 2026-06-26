export interface User {
  id: number
  email: string
  full_name: string
  role: string
  is_primary?: boolean
  is_active: boolean
  created_at: string
}

export interface Filter {
  id: number
  name: string
  is_active: boolean
  country: string | null
  city: string | null
  radius_km: number | null
  brands: string[]
  models: string[]
  fuel_types: string[]
  transmission_types: string[]
  price_min: number | null
  price_max: number | null
  mileage_min: number | null
  mileage_max: number | null
  year_min: number | null
  year_max: number | null
  min_match_score: number
  search_url: string | null
  include_keywords: string[]
  exclude_keywords: string[]
  created_at: string
  updated_at: string
}

export interface Listing {
  id: number
  external_id: string
  source: string
  url: string
  title: string
  price: number | null
  currency: string
  mileage: number | null
  year: number | null
  brand: string | null
  model: string | null
  fuel_type: string | null
  transmission: string | null
  description: string | null
  location: string | null
  seller_name: string | null
  images: string[]
  posted_time: string | null
  match_score: number
  status: string
  match_details: Record<string, number> | null
  is_duplicate: boolean
  notification_sent: boolean
  found_at: string
}

export interface DashboardStats {
  total_listings: number
  matched_listings: number
  today_listings: number
  notifications_sent: number
  active_filters: number
  system_status: string
  last_scan_at: string | null
  next_scan_at: string | null
  is_scanning: boolean
  monitoring_enabled: boolean
}

export interface MonitoringSettings {
  is_enabled: boolean
  refresh_interval_seconds: number
  refresh_interval_min_seconds: number
  refresh_interval_max_seconds: number
  last_scan_at: string | null
  next_scan_at: string | null
  is_scanning: boolean
  test_full_flow: boolean
}

export interface Notification {
  id: number
  listing_id: number
  recipient_email: string
  status: string
  delivery_result: string | null
  sent_at: string | null
  created_at: string
  listing_title: string | null
}

export interface ActivityLog {
  id: number
  category: string
  level: string
  message: string
  details: string | null
  source: string | null
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages?: number
}

export interface FilterTemplate {
  id: number
  name: string
  config_json: string
  created_at: string
  updated_at: string
}

export interface NotificationRecipient {
  id: number
  email: string
  name: string | null
  is_active: boolean
  created_at: string
}

export interface ChartDataPoint {
  date: string
  count: number
}

export interface DashboardCharts {
  listings_per_day: ChartDataPoint[]
  matches_per_day: ChartDataPoint[]
  notifications_per_day: ChartDataPoint[]
}

export interface ProductPost {
  id: number
  name: string
  description: string
  price: number | null
  currency: string
  images: string[]
  category?: string | null
  condition?: string
  availability?: string
  extra_details?: Record<string, string>
  schedule_date: string | null
  schedule_day: string | null
  schedule_time: string | null
  status: string
  is_queued?: boolean
  facebook_url: string | null
  error_message: string | null
  retry_count: number
  batch_label: string | null
  published_at: string | null
  created_at: string
  updated_at: string
}

export interface ProductStats {
  total: number
  pending: number
  scheduled: number
  published: number
  failed: number
  duplicate: number
  missing?: number
}
