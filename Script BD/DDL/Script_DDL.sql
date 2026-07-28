
---**********************************************************************************************
---**********************************************************************************************
---************************   CONFIGURACIONES   *************************************************
---**********************************************************************************************
---**********************************************************************************************
---**********************************************************************************************
---**********************************************************************************************

CREATE OR REPLACE TABLE `pruebahabi.config.parametros_ingesta` (
  nombre_archivo    STRING NOT NULL OPTIONS(description="Nombre del archivo a procesar"),
  tipo_archivo      STRING          OPTIONS(description="CSV, JSON, PARQUET, etc."),
  tabla_raw         STRING          OPTIONS(description="Tabla en capa raw"),
  tabla_staging     STRING          OPTIONS(description="Tabla en capa staging"),
  tipo_analisis     STRING          OPTIONS(description="ML, BI, REPORTING, etc.")
);


CREATE OR REPLACE TABLE `pruebahabi.config.parametros_consumption` (
  nombre_archivo    STRING NOT NULL OPTIONS(description="Archivo padre (FK lógica)"),
  tabla_consumption STRING NOT NULL OPTIONS(description="Tabla destino en consumption"),
  rol_tabla         STRING          OPTIONS(description="ML: FEATURES/TRAIN/TEST · BI: FACT/DIMENSION"),
  estrategia        STRING          OPTIONS(description="BI: SCD1/SCD2/NONE · ML: tipo de modelo"),
  clave             STRING          OPTIONS(description="ML: target · BI: business key"),
  orden_carga       INT64           OPTIONS(description="Orden de construcción"),
  activo            BOOL            OPTIONS(description="Habilita/deshabilita esta tabla")
)
CLUSTER BY nombre_archivo;




---**********************************************************************************************
---************************   AUDITORIA   *******************************************************
---**********************************************************************************************
CREATE OR REPLACE TABLE pruebahabi.metadata.ingestion_files (
  nombre_archivo    STRING     NOT NULL OPTIONS(description="Nombre del archivo procesado"),
  fuente            STRING     OPTIONS(description="Origen del archivo"),
  fecha_hora_inicio TIMESTAMP  OPTIONS(description="Inicio del procesamiento"),
  fecha_hora_fin    TIMESTAMP  OPTIONS(description="Fin del procesamiento"),
  estado            STRING     OPTIONS(description="Resultado: OK / ERROR"),
  filas_leidas      INT64      OPTIONS(description="Filas leídas del archivo"),
  filas_insertadas  INT64      OPTIONS(description="Filas insertadas en destino"),
  filas_rechazadas  INT64      OPTIONS(description="Filas rechazadas por validación"),
  mensaje_error     STRING     OPTIONS(description="Detalle del error si estado = ERROR")
)
PARTITION BY DATE(fecha_hora_inicio)
CLUSTER BY fuente, estado
OPTIONS(
  description="Metadatos de ingesta de archivos"
);
























---**********************************************************************************************
---**********************************************************************************************
---**********************************************************************************************
---*********************    TABLAS DE NEGOCIO   *************************************************
---**********************************************************************************************
---**********************************************************************************************
---**********************************************************************************************
---**********************************************************************************************
CREATE OR REPLACE TABLE `pruebahabi.raw.raw_transaccioneshabi` (
  id           STRING,
  ciudad       STRING,
  tipo         STRING,
  area_m2      STRING,
  alcobas      STRING,
  banos        STRING,
  precio_cop   STRING,
  lat          STRING,
  lon          STRING,
  fecha        STRING,
  estado       STRING,
  _loaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);


CREATE or replace TABLE  `pruebahabi.staging.stg_transaccioneshabi` (
  id         STRING NOT NULL,
  ciudad     STRING,
  tipo       STRING,
  area_m2    FLOAT64,
  alcobas    INT64,
  banos      INT64,
  precio_cop INT64,
  lat        FLOAT64,
  lon        FLOAT64,
  fecha      DATE,
  estado     STRING,
  _loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY fecha
CLUSTER BY ciudad, tipo;


CREATE OR REPLACE TABLE `pruebahabi.consumption.ml_features_transacciones` (
  propiedad_id      STRING NOT NULL,
  ciudad            STRING,
  tipo              STRING,
  estado            STRING,
  area_m2           FLOAT64,
  alcobas           INT64,
  banos             INT64,
  lat               FLOAT64,
  lon               FLOAT64,
  precio_por_m2     FLOAT64,
  log_precio_cop    FLOAT64,
  banos_por_alcoba  FLOAT64,
  area_por_alcoba   FLOAT64,
  anio              INT64,
  mes               INT64,
  trimestre         INT64,
  dia_semana        INT64,
  fecha             DATE,
  precio_cop        INT64,
  split             STRING,
  _feature_set_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY fecha
CLUSTER BY ciudad, tipo;

CREATE OR REPLACE TABLE `pruebahabi.consumption.ml_train_transacciones` (
  propiedad_id      STRING NOT NULL,
  ciudad            STRING,
  tipo              STRING,
  estado            STRING,
  area_m2           FLOAT64,
  alcobas           INT64,
  banos             INT64,
  lat               FLOAT64,
  lon               FLOAT64,
  precio_por_m2     FLOAT64,
  log_precio_cop    FLOAT64,
  banos_por_alcoba  FLOAT64,
  area_por_alcoba   FLOAT64,
  anio              INT64,
  mes               INT64,
  trimestre         INT64,
  dia_semana        INT64,
  fecha             DATE,
  precio_cop        INT64
)
PARTITION BY fecha
CLUSTER BY ciudad, tipo;

CREATE OR REPLACE TABLE `pruebahabi.consumption.ml_test_transacciones` (
  propiedad_id      STRING NOT NULL,
  ciudad            STRING,
  tipo              STRING,
  estado            STRING,
  area_m2           FLOAT64,
  alcobas           INT64,
  banos             INT64,
  lat               FLOAT64,
  lon               FLOAT64,
  precio_por_m2     FLOAT64,
  log_precio_cop    FLOAT64,
  banos_por_alcoba  FLOAT64,
  area_por_alcoba   FLOAT64,
  anio              INT64,
  mes               INT64,
  trimestre         INT64,
  dia_semana        INT64,
  fecha             DATE,
  precio_cop        INT64
)
PARTITION BY fecha
CLUSTER BY ciudad, tipo;






---*****************************************************************************
CREATE OR REPLACE TABLE `pruebahabi.raw.raw_macro_housing_index` (
  unit        STRING,
  country     STRING,
  month       STRING,
  price_index STRING,
  _loaded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);






CREATE OR REPLACE TABLE `pruebahabi.raw.raw_usa_transactions` (
  transaction_id            STRING,
  authority_name            STRING,
  property_state            STRING,
  property_fair_market_value STRING,
  property_type             STRING,
  transaction_type          STRING,
  transaction_date          STRING,
  lease_rate                STRING,
  sale_price                STRING,
  _loaded_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);