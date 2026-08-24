import io
p = "/isaac-sim/kit/python/lib/python3.12/site-packages/lightwheel_sdk/client/client.py"
s = io.open(p, encoding="utf-8").read()
if "status_code >= 500" in s:
    print("ya estaba parcheado"); raise SystemExit(0)
viejo = """                break
            except Exception as e:
                _ultimo = e
                self.logger.warning("POST %s: fallo de red %d/%d (%s)", url, _i + 1, _n, e)"""
nuevo = """                # Un 5xx es del servidor y es transitorio (Lightwheel devolvio 504 Gateway
                # Time-out el 2026-08-24 y tumbo una tirada desatendida de 6 h). El bucle salia
                # aqui en cuanto habia *respuesta*, fuese 200 o 504, asi que el reintento nunca
                # llegaba a usarse. Los 4xx si suben tal cual: no se arreglan repitiendo.
                if res.status_code >= 500 and _i + 1 < _n:
                    self.logger.warning("POST %s: HTTP %d, reintento %d/%d",
                                        url, res.status_code, _i + 1, _n)
                    time.sleep(_espera * (_i + 1))
                    continue
                break
            except Exception as e:
                _ultimo = e
                self.logger.warning("POST %s: fallo de red %d/%d (%s)", url, _i + 1, _n, e)"""
assert viejo in s, "bloque no encontrado"
s = s.replace(viejo, nuevo, 1).replace(
    "# se dejan subir tal cual. Ajustable:", "# tambien se reintentan (los 4xx no). Ajustable:", 1)
io.open(p, "w", encoding="utf-8").write(s)
print("parcheado")
