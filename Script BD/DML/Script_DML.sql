INSERT INTO `pruebahabi.config.parametros_ingesta`
  (nombre_archivo, tipo_archivo, tabla_raw, tabla_staging, tipo_analisis)
VALUES
  ('co_transacciones_habi.csv', 'CSV', 'raw_transaccioneshabi',   'stg_transaccioneshabi',   'ML'),
  ('macro_housing_index.xml',   'XML', 'raw_macro_housing_index', 'stg_macro_housing_index', 'ML');


INSERT INTO `pruebahabi.config.parametros_ingesta`
  (nombre_archivo, tipo_archivo, tabla_raw, tabla_staging, tipo_analisis)
VALUES
  ('usa_transactions_page_01.json', 'JSON', 'raw_usa_transactions', 'staging_usa_transactions', 'BI');





INSERT INTO `pruebahabi.metadata.parametros_consumption`
  (nombre_archivo, tabla_consumption, rol_tabla, estrategia, clave, orden_carga, activo)
VALUES
  -- co_transacciones_habi.csv  (target: precio_venta)
  ('co_transacciones_habi.csv', 'ml_features_transacciones', 'FEATURES', 'regresion', 'precio_venta', 1, TRUE),
  ('co_transacciones_habi.csv', 'ml_train_transacciones',    'TRAIN',    'regresion', 'precio_venta', 2, TRUE),
  ('co_transacciones_habi.csv', 'ml_test_transacciones',     'TEST',     'regresion', 'precio_venta', 3, TRUE),

  -- macro_housing_index.xml  (target: housing_index)
  ('macro_housing_index.xml', 'ml_features_macro_housing', 'FEATURES', 'series_temporales', 'housing_index', 1, TRUE),
  ('macro_housing_index.xml', 'ml_train_macro_housing',    'TRAIN',    'series_temporales', 'housing_index', 2, TRUE),
  ('macro_housing_index.xml', 'ml_test_macro_housing',     'TEST',     'series_temporales', 'housing_index', 3, TRUE);




