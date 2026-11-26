# Quorda Food Ordering System (Backend)

Quorda is a priority-driven food ordering and kitchen queue management backend system built with Django and Django REST Framework. A multi-factor priority algorithm organizes kitchen tickets and streamlines food preparation workflows for small to medium kitchens.

---

## Table of Contents

- [1. Overview and Project Aim](#1-overview-and-project-aim)
  - [1.1 Problem Statement](#11-problem-statement)
  - [1.2 Project Objectives](#12-project-objectives)
  - [1.3 System Architecture and UI Workspaces](#13-system-architecture-and-ui-workspaces)
  - [1.4 Repository and Development Scope](#14-repository-and-development-scope)
  - [1.5 Directory Structure](#15-directory-structure)
- [2. Technologies, Methodology and Challenges](#2-technologies-methodology-and-challenges)
  - [2.1 Technology Stack](#21-technology-stack)
  - [2.2 Prioritization Methodology](#22-prioritization-methodology)
    - [2.2.1 Core Mathematical Formulation](#221-core-mathematical-formulation)
    - [2.2.2 Arrival Aging and Batch Windowing (The 4th Factor)](#222-arrival-aging-and-batch-windowing-the-4th-factor)
    - [2.2.3 Edge Cases and Batch Rebalancing](#223-edge-cases-and-batch-rebalancing)
    - [2.2.4 Simple Order Detection](#224-simple-order-detection)
    - [2.2.5 VIP and Escalated Orders](#225-vip-and-escalated-orders)
  - [2.3 Architectural Challenges and Solutions](#23-architectural-challenges-and-solutions)
- [3. Tests and Results for a Food Ordering System with This Scale (MVP)](#3-tests-and-results-for-a-food-ordering-system-with-this-scale-mvp)
  - [3.1 Automated Test Suite](#31-automated-test-suite)
  - [3.2 In-Process API Performance Benchmark](#32-in-process-api-performance-benchmark)
    - [3.2.1 Scaling and Latency Results](#321-scaling-and-latency-results)
    - [3.2.2 Pure Algorithm Computational Cost](#322-pure-algorithm-computational-cost)
  - [3.3 Concurrent Load Testing (Locust)](#33-concurrent-load-testing-locust)
  - [3.4 Benchmark on PostgreSQL 16](#34-benchmark-on-postgresql-16)
  - [3.5 Production Feasibility and MVP Conclusion](#36-production-feasibility-and-mvp-conclusion)
- [4. Table of Endpoints and Functionalities](#4-table-of-endpoints-and-functionalities)
  - [4.1 Authentication and Account Management](#41-authentication-and-account-management)
  - [4.2 Restaurant Profiles and Staff Operations](#42-restaurant-profiles-and-staff-operations)
  - [4.3 Catalog, Shifts and Kitchen Configuration](#43-catalog-shifts-and-kitchen-configuration)
  - [4.4 Cart and Checkout](#44-cart-and-checkout)
  - [4.5 Kitchen Display and Order Processing](#45-kitchen-display-and-order-processing)
  - [4.6 Batch Lifecycle and Rebalancing](#46-batch-lifecycle-and-rebalancing)
  - [4.7 Customer Delivery Orders](#47-customer-delivery-orders)
- [5. Future Work](#5-future-work)
  - [5.1 Restaurant Inventory Management](#51-restaurant-inventory-management)
  - [5.2 Enhanced Sorting Combinations](#52-enhanced-sorting-combinations)
  - [5.3 Startup Supplier Recommendation and Decision Pipeline](#53-startup-supplier-recommendation-and-decision-pipeline)
- [Installation and Setup](#installation-and-setup)

---

## 1. Overview and Project Aim

### 1.1 Problem Statement
 kitchens operate in high-pressure, time-sensitive environments. Traditional order fulfillment workflows rely primarily on two paradigms:

1. **Strict First-In, First-Out (FIFO):** Kitchens prepare tickets in the exact chronological sequence in which orders are submitted. Under FIFO, a high-complexity order requiring 25 minutes of preparation can stall low-complexity orders (such as single beverages, sides, or quick snacks), leading to artificial bottlenecks and inflated wait times across the floor.
2. **Naked-Eye Triage:** Kitchen staff visually scan paper receipts or display tickets, attempting to mentally group similar items and estimate preparation times. This approach is prone to cognitive fatigue, human bias, skipped tickets, and inconsistent service levels during peak operational rushes.

### 1.2 Project Objectives

Quorda addresses these challenges by introducing a deterministic, algorithmic priority framework that balances operational efficiency with fairness:

- **Algorithmic Prioritization:** Orders are assigned an automated priority score based on preparation duration, item quantities, and meal category significance.
- **Fairness with priority:** Batch windowing keeps earlier tickets ahead of later batches, while priority scoring orders tickets inside a batch. A higher score does not move an order into an older batch.
- **Target Audience:** The system is tailored as an MVP (Minimum Viable Product) for small to medium-sized kitchens, food trucks, and independent diners experiencing peak-hour congestion.

### 1.3 System Architecture and UI Workspaces

The Quorda backend provides dedicated query mechanisms that support specialized dashboard views on the frontend kitchen display unit (KDS), avoiding a monolithic single-column order list:

1. **Indoor Windowed Queue:** Active dine-in orders structured into chronological batches and sorted internally by priority score.
2. **Outdoor Windowed Queue:** Delivery and pickup orders grouped into chronological batches, enabling kitchen staff to balance external couriers alongside in-house dining.
3. **Simple Orders Fast-Track:** Isolated view displaying small, high-throughput orders (e.g., drinks, single pastries, cold appetizers) that can be cleared immediately without disrupting cooking stations.
4. **VIP and Escalated Orders:** Flagged tickets requiring immediate kitchen intervention, processed chronologically ahead of standard batch pools.
5. **Universal Filtered Orders Workspace:** Configurable administrative interface supporting multi-parameter filtering (status, dining mode, custom sorting) for floor managers and dispatchers.

### 1.4 Repository and Development Scope

- **Backend Repository (Current):** RESTful API built in Python with Django and Django REST Framework, encapsulating the database schema, batching logic, prioritization engine, authentication, and performance benchmark suites.
- **Frontend Repository:** Developed with React, consuming these REST endpoints to render dynamic kitchen display panels.

### 1.5 Directory Structure

```
quorda/
|-- apps/
|   |-- cart/               # Customer shopping cart, line item updates, and checkout flow
|   |   |-- models/         # Cart and CartItem models
|   |   |-- serializers.py  # Cart validation and payload mappings
|   |   |-- services.py     # Cart business logic and TTL expiration
|   |   |-- views.py        # Cart endpoints
|   |-- common/             # Cross-cutting concerns, shared pagination, management commands
|   |   |-- pagination.py   # PageNumberPagination implementation
|   |   |-- management/     # Commands: seed_data, expire_carts
|   |-- orders/             # Core priority, batching, and kitchen processing app
|   |   |-- helpers/        # PriorityCalculator, OrderSorter, SimpleOrderDetector
|   |   |-- models/         # Order, OrderItem, and database index definitions
|   |   |-- services/       # OrderService, BatchService, CustomerOrderService
|   |   |-- views/          # Kitchen queue views, batch operations, item views
|   |-- restaurants/        # Restaurant configuration and menu management
|   |   |-- models/         # RestaurantProfile, Category, MenuItem, Criteria, ShiftDefinition
|   |   |-- services.py     # Menu and criteria administration logic
|   |   |-- views.py        # Public and owner catalog endpoints
|   |-- users/              # Authentication, RBAC, cashier and profile management
|       |-- models/         # Custom User model, CashierProfile
|       |-- views/          # JWT auth views, cashier permission controls
|-- config/                 # Project configuration and settings modules
|   |-- settings/
|   |   |-- base.py         # Common Django settings and DRF configuration
|   |   |-- local.py        # Local development settings (PostgreSQL)
|   |   |-- perf.py         # Self-contained SQLite setting for benchmarks
|   |   |-- test.py         # Unit testing configuration
|   |-- urls.py             # Root URL routing and OpenAPI/Swagger schema setup
|-- perf/                   # Benchmarking and load testing harness
|   |-- benchmark_api.py    # In-process ORM scaling and N+1 query benchmark
|   |-- locustfile.py       # Multi-user concurrent load test scenario
|   |-- results/            # Benchmark outputs, CSVs, and PDF analytical reports
|-- manage.py
|-- requirements.txt        # Production dependencies
|-- requirements.local.txt  # Development, testing, and benchmarking dependencies
|-- docker-compose.yml      # Local container orchestration
```

---

## 2. Technologies, Methodology and Challenges

### 2.1 Technology Stack

- **Language:** Python 3.13
- **Framework:** Django 6.0 / Django REST Framework (DRF) 3.17
- **Authentication:** JSON Web Tokens (JWT) via `djangorestframework-simplejwt`
- **Database:** PostgreSQL 16 (Production/Development), SQLite in-memory (Automated Benchmarking)
- **API Documentation:** OpenAPI 3.0 via `drf-spectacular` (Swagger UI and ReDoc)
- **Load and Performance Testing:** Locust 2.47, Python `unittest` harness

### 2.2 Prioritization Methodology

#### 2.2.1 Core Mathematical Formulation

Every order entering the Quorda system receives an automated `priority_score` between 0.0 and 1.0 (given weights that sum to 1). The score is computed by `PriorityCalculator` from three weighted factors:

1. **Total Preparation Time ($`T`$):** the aggregated preparation duration of all line items.

   ```math
   T = \sum_{i=1}^{n} \text{prep time}_i \times \text{quantity}_i
   ```

   The inverse preparation score rewards quick-to-prepare orders:

   ```math
   \text{time score} = \min\left(\frac{2.0}{T + 1},\ 1.0\right)
   ```

2. **Total Quantity ($`Q`$):** the total item count on the ticket.

   ```math
   Q = \sum_{i=1}^{n} \text{quantity}_i
   ```

   The inverse quantity score rewards lightweight tickets:

   ```math
   \text{quantity score} = \min\left(\frac{2.0}{Q + 1},\ 1.0\right)
   ```

3. **Maximum Category Priority ($`C_{\max}`$):** menu items belong to categories with an integer priority from 1 (lowest) to 5 (highest).

   ```math
   C_{\max} = \max_{i=1}^{n} \text{category priority}_i
   ```

   It is normalized to the range 0 to 1:

   ```math
   \text{category score} =
   \begin{cases}
   \dfrac{C_{\max} - 1}{4}, & \text{if at least one item has a category} \\[6pt]
   0.0, & \text{otherwise}
   \end{cases}
   ```

The final `priority_score` is a weighted linear combination of the three normalized terms:

```math
\text{priority score} =
w_{\text{time}} \cdot \text{time score} +
w_{\text{quantity}} \cdot \text{quantity score} +
w_{\text{category}} \cdot \text{category score}
```

- **Default weights:** $`w_{\text{time}} = 0.4`$, $`w_{\text{quantity}} = 0.4`$, $`w_{\text{category}} = 0.2`$, so that $`w_{\text{time}} + w_{\text{quantity}} + w_{\text{category}} = 1.0`$.
- **Customizability:** weights can be reconfigured per restaurant through the `/api/v1/restaurants/calculation-params/` endpoint to match different kitchen strategies (for example, favoring preparation speed over category tiering).

#### 2.2.2 Arrival Aging and Batch Windowing (The 4th Factor)

If orders were ranked globally based purely on `priority_score`, high-priority orders arriving during continuous rushes would perpetually preempt earlier orders. For example, order 99 (a single espresso) would immediately jump ahead of order 8 (a family dinner placed 20 minutes prior), leading to severe starvation of earlier orders.

To resolve this without sacrificing the benefits of priority sorting, Quorda introduces **Batch Windowing** as the 4th factor:

- Active orders are partitioned into chronological buckets called **Batches** of fixed window size $W$ (default: 10 orders).
- The `batch_number` is assigned atomically upon order insertion.
- When an order arrives, it joins the newest active batch if that batch contains fewer than $W$ pending orders; otherwise, it initiates batch $B + 1$.
- New orders are permanently restricted from joining older batches.
- The kitchen display sorts orders by:
  1. `batch_number ASC` (Older batches must be cleared first)
  2. `special_flag DESC` (VIP status within the batch)
  3. `priority_score DESC` (Smart heuristic ordering within the batch)
  4. `created_at ASC` (Chronological tie-breaker)

Under this system, order 99 assigned to Batch 2 can never jump ahead of order 8 residing in Batch 1, regardless of how high its priority score is.

#### 2.2.3 Edge Cases and Batch Rebalancing

When orders in earlier batches are finished out of sequence or cancelled, empty slots ("holes") emerge. The `rebalance_batches` routine resolves this atomically:
- Locks the restaurant record (`select_for_update`) to prevent concurrent race conditions.
- Scans active batches from lowest to highest and promotes the oldest pending tickets from subsequent batches into open slots.
- Cascades promotions left-to-right, keeping batches at target capacity while preserving arrival seniority.

#### 2.2.4 Simple Order Detection

Fast-turnaround items (beverages, cold sides, ready-made snacks) can bypass the main hot-line queue. Restaurants configure simple-order criteria based on maximum total quantity and minimum category priority. The detector evaluates these directly within database queries, routing eligible tickets to dedicated express/expo counters.

#### 2.2.5 VIP and Escalated Orders

Tickets requiring immediate intervention can be marked with `special_flag = True` by authorized staff. VIP orders bypass score ranking and are placed at the front of their batch, sorted chronologically (`created_at ASC`).

### 2.3 Architectural Challenges and Solutions

- **N+1 Query Elimination:** Nested order items, menu items, and categories are retrieved using an optimized prefetch strategy, locking read overhead to a constant 3 SQL queries regardless of order volume.
- **Concurrent Batch Serialization:** High-frequency order creation and rebalance operations are serialized safely using PostgreSQL row-level locks on `RestaurantProfile`.
- **Database-Level Sorting & Pagination:** Priority sorting and batch boundaries are executed directly via database indexes and lazy querysets, ensuring memory efficiency during high-volume periods.

---

## 3. Tests and Results for a Food Ordering System with This Scale (MVP)

Quorda was subjected to validation across unit functionality, in-process ORM scaling benchmarks, and multi-user concurrent load simulations.

### 3.1 Automated Test Suite

The test suite covers models, serializers, service layers, batch rebalancing, simple order detection, and permission boundaries:

- `test_priority_calculator.py`: Verifies mathematical boundary conditions ($[0.0, 1.0]$), weight changes, zero-item handling, and sensitivity to preparation time and quantity.
- `test_order_sorter.py`: Validates batch assignment logic, prevention of backward batch sliding, and sort tuple keys.

- `test_simple_order_detector.py`: Validates ORM aggregation filters against varying quantity thresholds and category priorities.
- `test_customer_order_service.py` & `test_customer_views.py`: Validates delivery order creation, customer ownership checks, and cancellation state machines.

### 3.2 In-Process API Performance Benchmark

The benchmark harness (`perf/benchmark_api.py`) tests 25 endpoints (16 read, 9 write) across database sizes of 100, 500, 1,000, and 2,000 orders using isolated SQLite instances to evaluate query growth, N+1 patterns, and p95 latency.

#### 3.2.1 Scaling and Latency Results

Benchmark metrics from `Quorda_API_Performance_Benchmark_Report.pdf`:

| Endpoint | Type | 100 Orders (p95) | 500 Orders (p95) | 1,000 Orders (p95) | 2,000 Orders (p95) | SQL Queries | Growth Ratio |
|---|---|---|---|---|---|---|---|
| **GET indoor normal windowed** | Read | 84.3 ms | 56.0 ms | 52.3 ms | 39.0 ms | 3 | x0.5 |
| **GET outdoor normal windowed** | Read | 60.0 ms | 47.7 ms | 146.5 ms | 37.9 ms | 3 | x0.6 |
| **GET vip** | Read | 34.8 ms | 28.4 ms | 32.6 ms | 8.3 ms | 1 - 3 | x0.2 |
| **GET simple** | Read | 107.0 ms | 55.9 ms | 116.3 ms | 46.2 ms | 3 | x0.4 |
| **GET filtered** | Read | 80.2 ms | 70.3 ms | 87.0 ms | 69.1 ms | 3 | x0.9 |
| **GET orders (list)** | Read | 41.9 ms | 66.8 ms | 65.8 ms | 43.3 ms | 3 | x1.0 |
| **GET batch summary** | Read | 6.3 ms | 5.7 ms | 18.4 ms | 19.7 ms | 1 | x3.1 |
| **GET customer orders** | Read | 26.1 ms | 16.8 ms | 20.6 ms | 36.7 ms | 3 | x1.4 |
| **POST create order (dine-in)** | Write | 41.9 ms | 45.6 ms | 89.3 ms | 52.7 ms | 12 | x1.3 |
| **POST place delivery order** | Write | 60.9 ms | 85.8 ms | 68.4 ms | 54.3 ms | 13 | x0.9 |
| **POST add order item** | Write | 62.6 ms | 57.1 ms | 61.6 ms | 36.6 ms | 8 | x0.6 |
| **POST batch rebalance** | Write | 99.6 ms | 66.6 ms | 142.5 ms | 162.0 ms | 6 | x1.6 |
| **POST batch reset** | Write | 14.8 ms | 14.2 ms | 17.6 ms | 38.4 ms | 4 | x2.6 |

Key Findings:
- **Zero N+1 Queries:** Read query counts stay constant (1 to 3 queries) across all data scales.
- **Latency Stability:** 24 of 25 endpoints remain under 70 ms p95 at 2,000 orders. Order creation maintains a constant ~31 ms p50.
- **Operational Hotspot:** `POST batch rebalance` scales to 162.0 ms at 2,000 orders due to payload serialization (growing from 0.9 KB to 8.4 KB) while queries remain flat at 6.

#### 3.2.2 Pure Algorithm Computational Cost

In-memory benchmark of scoring and batch sorting without database or network overhead:

| Orders Processed | Total Scoring Time | Time Per Order | Batch Sorting Time |
|---|---|---|---|
| **1,000 Orders** | 8.2 ms | ~8.2 microseconds | 1.2 ms |
| **10,000 Orders** | 91.3 ms | ~9.1 microseconds | 14.9 ms |
| **50,000 Orders** | 456.9 ms | ~9.1 microseconds | 71.1 ms |

The scoring engine scales linearly at ~9 microseconds per order ($O(n)$), and batch sorting 50,000 orders requires only 71.1 ms ($O(n \log n)$), confirming that the algorithmic layer adds negligible computational cost.

### 3.3 Concurrent Load Testing (Locust)

End-to-end load tests (`perf/locustfile.py`) simulated realistic multi-persona traffic (kitchen displays, cashiers, customers, owners, and cart shoppers):

| Metric | 10 Concurrent Users | 50 Concurrent Users (Peak Load) |
|---|---|---|
| **Duration** | 15 min 3 s | 9 min 58 s |
| **Total Requests** | 1,383 requests | 4,408 requests |
| **Failure Rate** | 0 failures (0.0%) | 0 failures (0.0%) |
| **Throughput** | 1.53 requests/s | 7.36 requests/s |
| **Median (p50) / p95 Latency** | 110 ms / 180 ms | 200 ms / 1,200 ms |
| **Kitchen Board (p95)** | 180 ms (avg 123 ms) | 1,000 ms (avg 341 ms) |
| **Order Creation (Dine-in Avg)** | 138 ms | 415 ms |
| **Max Outlier Latency** | 2,161 ms (auth hashing) | 5,620 ms (concurrent write spikes) |

Both test runs maintained a 0% failure rate under sustained load. Elevated p95/max latencies were primarily driven by cryptographic password hashing during authentication and large payload serializations during batch rebalances.

### 3.4 Benchmark on PostgreSQL 16

The same harness was run against PostgreSQL 16. With 2,000 orders in the database, 23 of 25 endpoints have a p95 under 30 ms and 24 of 25 under 50 ms; the slowest is `POST batch rebalance` (p95 about 82 ms, median 22 ms). No endpoint issues N+1 queries: reads use at most 3 SQL queries at every data size. All 325 tests also pass on PostgreSQL, and CI runs them there.

### 3.5 Production Feasibility and MVP Conclusion

The test results show that Quorda works well as an MVP for small to medium kitchens:
- **Reliable Under Load:** The system handled concurrent traffic without dropping or failing any requests.
- **Good Fit for Small and Medium Kitchens:** The performance is well suited for kitchens handling 500 to 2,000 active orders per service without database slowdowns.
- **Testing Improvements:** The current tests give a solid early evaluation, but the testing techniques and tools can be improved in future stages (such as testing on dedicated production servers instead of local runs) to get more accurate and realistic results.
- **Next Scaling Steps:** As the system grows, adding background task workers (such as Celery and Redis) to handle batch rebalancing and using database connection pooling will help support bigger kitchen workloads smoothly.

---

## 4. Table of Endpoints and Functionalities

All endpoints are versioned under the `/api/v1/` prefix.

### 4.1 Authentication and Account Management

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | Public | Register a new customer or restaurant owner user account |
| `POST` | `/api/v1/auth/login/` | Public | Authenticate credentials and obtain JWT access and refresh token pair |
| `POST` | `/api/v1/auth/refresh/` | Public | Obtain a refreshed JWT access token using a valid refresh token |
| `POST` | `/api/v1/auth/logout/` | Authenticated | Invalidate and blacklist the current refresh token |
| `GET` | `/api/v1/users/` | Admin | List all registered user accounts in the platform |
| `GET` | `/api/v1/users/me/` | Authenticated | Retrieve authenticated user profile and account details |
| `PUT` | `/api/v1/users/me/` | Authenticated | Full update of the current user profile |
| `PATCH` | `/api/v1/users/me/` | Authenticated | Partial update of the current user profile |

### 4.2 Restaurant Profiles and Staff Operations

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/restaurant-profiles/` | Owner | Retrieve own restaurant profile, address, and operational metadata |
| `PUT` | `/api/v1/restaurant-profiles/` | Owner | Full update of own restaurant profile |
| `PATCH` | `/api/v1/restaurant-profiles/` | Owner | Partial update of own restaurant profile |
| `GET` | `/api/v1/restaurant-profiles/<uuid:user_id>/` | Admin | Administrative retrieval of a specific restaurant profile |
| `GET` | `/api/v1/cashiers/` | Owner | List all cashier accounts assigned to the restaurant |
| `POST` | `/api/v1/cashiers/` | Owner | Provision a new cashier account linked to the restaurant |
| `GET` | `/api/v1/cashiers/<uuid:pk>/` | Owner | Retrieve details and status of a specific cashier |
| `PUT` | `/api/v1/cashiers/<uuid:pk>/` | Owner | Full update of cashier details |
| `PATCH` | `/api/v1/cashiers/<uuid:pk>/` | Owner | Partial update of cashier details (e.g., active status) |
| `DELETE` | `/api/v1/cashiers/<uuid:pk>/` | Owner | Deactivate or delete a cashier profile |
| `POST` | `/api/v1/cashiers/set-vip-permission/` | Owner | Grant or revoke cashier authorization to mark orders with the VIP flag |

### 4.3 Catalog, Shifts and Kitchen Configuration

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/restaurants/` | Public | List all active restaurants |
| `GET` | `/api/v1/restaurants/<uuid:pk>/` | Public | Retrieve public details and opening hours for a restaurant |
| `GET` | `/api/v1/restaurants/<uuid:pk>/menu-items/` | Public | Retrieve published menu items grouped by category for a restaurant |
| `GET` | `/api/v1/restaurants/categories/` | Owner | List menu item categories defined for the restaurant |
| `POST` | `/api/v1/restaurants/categories/` | Owner | Create a new menu category with priority ranking (1 to 5) |
| `GET` | `/api/v1/restaurants/categories/<uuid:pk>/` | Owner | Retrieve details of a specific food category |
| `PUT` | `/api/v1/restaurants/categories/<uuid:pk>/` | Owner | Full update of category name or priority level |
| `PATCH` | `/api/v1/restaurants/categories/<uuid:pk>/` | Owner | Partial update of category properties |
| `DELETE` | `/api/v1/restaurants/categories/<uuid:pk>/` | Owner | Delete a category |
| `GET` | `/api/v1/restaurants/menu-items/` | Owner | List all menu items owned by the restaurant |
| `POST` | `/api/v1/restaurants/menu-items/` | Owner | Create a menu item with prep time, pricing, and category mapping |
| `GET` | `/api/v1/restaurants/menu-items/<uuid:pk>/` | Owner | Retrieve menu item specifications |
| `PUT` | `/api/v1/restaurants/menu-items/<uuid:pk>/` | Owner | Full update of menu item attributes |
| `PATCH` | `/api/v1/restaurants/menu-items/<uuid:pk>/` | Owner | Partial update of price, prep time, or category |
| `DELETE` | `/api/v1/restaurants/menu-items/<uuid:pk>/` | Owner | Remove a menu item from the catalog |
| `GET` | `/api/v1/restaurants/criteria/` | Owner | Retrieve simple-order detection rules (`max_quantity`, `min_category_priority`) |
| `POST` | `/api/v1/restaurants/criteria/` | Owner | Configure initial simple-order criteria |
| `PUT` | `/api/v1/restaurants/criteria/` | Owner | Replace simple-order criteria thresholds |
| `PATCH` | `/api/v1/restaurants/criteria/` | Owner | Adjust specific criteria thresholds |
| `GET` | `/api/v1/restaurants/calculation-params/` | Owner | View priority formula weights ($`\texttt{w_{\text{time}}}`$, $`\texttt{w_{\text{quantity}}}`$, $`\texttt{w_{\text{category}}}`$) |
| `POST` | `/api/v1/restaurants/calculation-params/` | Owner | Set custom formula weights (must sum to 1.0) |
| `PUT` | `/api/v1/restaurants/calculation-params/` | Owner | Replace custom formula weights |
| `PATCH` | `/api/v1/restaurants/calculation-params/` | Owner | Update individual formula weights |
| `GET` | `/api/v1/restaurants/shifts/` | Owner | List operational shifts defined for the kitchen |
| `POST` | `/api/v1/restaurants/shifts/` | Owner | Create a work shift with designated start and end times |
| `GET` | `/api/v1/restaurants/shifts/<uuid:pk>/` | Owner | Retrieve shift configuration details |
| `PUT` | `/api/v1/restaurants/shifts/<uuid:pk>/` | Owner | Full update of shift schedules |
| `PATCH` | `/api/v1/restaurants/shifts/<uuid:pk>/` | Owner | Partial adjustment of shift schedules |
| `DELETE` | `/api/v1/restaurants/shifts/<uuid:pk>/` | Owner | Delete a shift definition |

### 4.4 Cart and Checkout

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/cart/` | Customer | Retrieve active shopping cart contents, line items, and estimated cost |
| `DELETE` | `/api/v1/cart/` | Customer | Clear all items from the current active shopping cart |
| `POST` | `/api/v1/cart/items/` | Customer | Add a menu item with specified quantity to the shopping cart |
| `GET` | `/api/v1/cart/items/<uuid:item_id>/` | Customer | Inspect details of an item in the cart |
| `PATCH` | `/api/v1/cart/items/<uuid:item_id>/` | Customer | Update quantity for an existing cart item |
| `DELETE` | `/api/v1/cart/items/<uuid:item_id>/` | Customer | Remove a specific item from the shopping cart |
| `POST` | `/api/v1/cart/checkout/` | Customer | Convert active cart into an outdoor delivery order and trigger priority calculation |

### 4.5 Kitchen Display and Order Processing

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/orders/` | Staff/Owner | Retrieve paginated list of restaurant orders with custom ordering |
| `POST` | `/api/v1/orders/` | Staff/Owner | Create an indoor dine-in order, assign items, and allocate `batch_number` |
| `GET` | `/api/v1/orders/indoor/normal/windowed/` | Staff/Owner | Windowed kitchen queue for indoor normal orders (sorted: batch -> score -> created) |
| `GET` | `/api/v1/orders/outdoor/normal/windowed/` | Staff/Owner | Windowed kitchen queue for outdoor delivery orders |
| `GET` | `/api/v1/orders/vip/` | Staff/Owner | Dedicated windowed queue for VIP-flagged tickets (sorted chronologically) |
| `GET` | `/api/v1/orders/simple/` | Staff/Owner | Fast-track order list matching defined simple-order criteria |
| `GET` | `/api/v1/orders/filtered/` | Staff/Owner | Universal query endpoint supporting combinations of status, scope, and dining mode |
| `GET` | `/api/v1/orders/<uuid:pk>/` | Staff/Owner | Retrieve detailed ticket info, lines, prep time, and calculated priority score |
| `PUT` | `/api/v1/orders/<uuid:pk>/` | Staff/Owner | Full update of an editable (pending) order ticket |
| `PATCH` | `/api/v1/orders/<uuid:pk>/` | Staff/Owner | Partial update of an order (e.g., mark status as `done` or `cancelled`) |
| `DELETE` | `/api/v1/orders/<uuid:pk>/` | Staff/Owner | Cancel or delete an active order |
| `GET` | `/api/v1/orders/<uuid:order_pk>/items/` | Staff/Owner | List all line items belonging to a specific order |
| `POST` | `/api/v1/orders/<uuid:order_pk>/items/` | Staff/Owner | Append an item to an active order and trigger score recalculation |
| `GET` | `/api/v1/orders/<uuid:order_pk>/items/<uuid:pk>/` | Staff/Owner | Retrieve line item details |
| `PUT` | `/api/v1/orders/<uuid:order_pk>/items/<uuid:pk>/` | Staff/Owner | Replace an order line item |
| `PATCH` | `/api/v1/orders/<uuid:order_pk>/items/<uuid:pk>/` | Staff/Owner | Update quantity or menu item reference on an active order |
| `DELETE` | `/api/v1/orders/<uuid:order_pk>/items/<uuid:pk>/` | Staff/Owner | Remove a line item and recalculate overall ticket priority score |

### 4.6 Batch Lifecycle and Rebalancing

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/orders/batch/summary/` | Staff/Owner | Return active batch summary with pending counts and available hole capacities |
| `POST` | `/api/v1/orders/batch/rebalance/` | Staff/Owner | Trigger cascading left-to-right promotion of oldest orders to fill batch holes |
| `POST` | `/api/v1/orders/batch/reset/` | Staff/Owner | Reset batch numbers (`mode=completed` for finished orders, `mode=all` between shifts) |

### 4.7 Customer Delivery Orders

| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/orders/customers/` | Customer | List all delivery orders placed by the authenticated customer |
| `POST` | `/api/v1/orders/customers/` | Customer | Place a direct delivery order with specified delivery destination |
| `GET` | `/api/v1/orders/customers/<uuid:pk>/` | Customer | View real-time tracking status and details of own order |
| `PATCH` | `/api/v1/orders/customers/<uuid:pk>/` | Customer | Modify items on a pending delivery order |
| `POST` | `/api/v1/orders/customers/<uuid:pk>/cancel/` | Customer | Cancel a pending delivery order before kitchen preparation commences |

---

## 5. Future Work

To transition Quorda from a kitchen queue MVP into a comprehensive restaurant operations platform, future development focuses on three primary expansion tracks:

### 5.1 Restaurant Inventory Management
Scaling the system to add inventory and raw material management features. This will help restaurants easily track their ingredients and stock levels in real time alongside incoming orders.

### 5.2 Enhanced Sorting Combinations
Researching and testing advanced sorting combinations to calculate order priorities with even greater efficiency. The current multi-factor algorithm serves as a validated starting point that delivers substantially more fairness than classic FIFO queuing and the traditional practice of sorting paper receipts by naked eye. Future iterations will explore expanded heuristics and dynamic parameter combinations to adapt to shifting kitchen loads.

### 5.3 Startup Supplier Recommendation and Decision Pipeline
Scaling Quorda to empower new food startups and small restaurants by introducing an automated supplier matching pipeline. Rather than functioning strictly as an internal kitchen management tool, this workflow adds an entirely new decision-making layer that connects restaurant owners directly with the best raw material and ingredient suppliers.

Key objectives of the supplier pipeline:
- **Intelligent Provider Matching:** Evaluates local material suppliers based on budget boundaries, operational size, and target market segments.
- **Data-Driven Market Insights:** Ingests anonymized performance data from established restaurants within the same geographic cluster to help emerging kitchens make informed procurement choices.
- **Ecosystem Integration:** Connects suppliers directly to restaurant owners, evolving Quorda into an end-to-end platform for ordering, queue management, and procurement decision-making.

---

## Installation and Setup

### Prerequisites

- Python 3.13 or higher
- PostgreSQL 16 (or local SQLite for lightweight testing)
- Virtual environment tool (`venv`)

### 1. Clone the Repository

```bash
git clone https://github.com/H-Atef/quorda-django.git
```

### 2. Configure Environment

Create a virtual environment and install the required dependencies:

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.local.txt
```

Configure your `.env` file in the project root:

```env
SECRET_KEY=your-long-random-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000
DB_NAME=<DB>
DB_USER=<USER>
DB_PASSWORD=<PASSWORD>
DB_HOST=localhost
DB_PORT=5432
```

`.env.example` lists every variable. `SECRET_KEY` is required (the app refuses to start without it), `DEBUG` defaults to `False` when unset, and with `DEBUG=False` browser origins must be listed in `CORS_ALLOWED_ORIGINS`. To run everything in containers instead: `cp .env.example .env && docker compose up --build`.

### 3. Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Start the Development Server

```bash
python manage.py runserver 8000
```

The interactive API documentation is available at:
- **Swagger UI:** `http://localhost:8000/api/schema/swagger-ui/`
- **ReDoc:** `http://localhost:8000/api/schema/redoc/`
- **OpenAPI Schema:** `http://localhost:8000/api/schema/`

### 5. Running Tests and Benchmarks

Execute the unit test suite:
```bash
python manage.py test apps --settings=config.settings.test   # SQLite, no setup needed
python manage.py test apps                                    # PostgreSQL (needs .env)
```

Execute the in-process performance benchmark:
```bash
python perf/benchmark_api.py
```

Run concurrent load tests with Locust:
```bash
locust -f perf/locustfile.py --host http://localhost:8000
```