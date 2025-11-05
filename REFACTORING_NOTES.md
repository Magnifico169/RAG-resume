# Описание рефакторинга RAG Pipeline в контексте функционального программирования

## Общее описание системы

### Что это

**Система анализа релевантности резюме** — веб-приложение для автоматической оценки соответствия резюме кандидатов требованиям вакансий с использованием технологий RAG (Retrieval-Augmented Generation) и OpenAI GPT API.

### Для чего предназначена

Система решает следующие задачи:

- **Управление резюме**: Создание, хранение и просмотр резюме кандидатов
- **Управление вакансиями**: Создание и хранение описаний вакансий с требованиями
- **Автоматический анализ**: Оценка соответствия резюме вакансии с помощью ИИ
- **Хранение результатов**: Сохранение истории анализов в оперативной памяти для последующего просмотра (данные теряются при перезапуске приложения)
- **Аутентификация**: Система ролей (user/admin) с защитой доступа
- **Импорт данных**: Поддержка импорта резюме из формата hh.ru

### Как работает

Система построена на архитектуре клиент-сервер с асинхронной обработкой запросов:

```
Клиент → HTTP Request → aiohttp Server → Обработчики → RAG Analyzer → OpenAI API → Результат
```

**Основные компоненты:**

1. **HTTP-сервер** (aiohttp): Принимает HTTP-запросы, обрабатывает маршрутизацию
2. **Обработчики запросов**: Валидируют данные, извлекают информацию из хранилища
3. **RAG Analyzer**: Подготавливает контекст, вызывает OpenAI API, обрабатывает результаты
4. **Хранилище данных (оперативная память)**: Управляет данными в памяти (резюме, вакансии, анализы, пользователи, логи). Все данные хранятся только в оперативной памяти и не сохраняются на диск.
5. **Модели данных** (Pydantic): Валидируют структуру входящих и исходящих данных

**Поток обработки запроса:**

```
HTTP Request 
  → Middleware (логирование, аутентификация)
  → Handler (валидация, извлечение параметров)
  → Storage (получение данных)
  → RAG Analyzer (анализ)
  → Storage (сохранение результата)
  → HTTP Response
```

---

## Обработка информации

### Общая схема обработки данных

**Входные данные:**

```
Вход ::= 
  HTTPRequest 
    • { method, path, headers, body }
    • { resume_data, job_data, user_data, ... }
```


## Выявленные ошибки и проблемы

### Проблемы функционального программирования

**1. Нарушение принципов чистоты функций:**

```
Проблема ::=
  Методы класса MemoryStorage содержат побочные эффекты
    • _read_data() → обращение к self._data
    • _write_data() → мутация self._data
    • методы зависят от состояния класса

Проявление:
  Метод → зависит_от(self._data) → побочный_эффект(мутация_состояния)
```

**2. Смешение чистых и нечистых операций:**

```
Проблема ::=
  В одном классе смешаны
    • операции с побочными эффектами (мутация self._data)
    • чистые функции (enrich_item_with_metadata)
    • сложно отделить чистую логику от состояния

Проявление:
  MemoryStorage ::=
    self._data (состояние)
    • _read_data() (зависит от состояния)
    • _write_data() (мутирует состояние)
    • enrich_item_with_metadata() (чистая функция, но в классе)
```

**3. Императивные паттерны в обработке:**

```
Проблема ::=
  Использование императивных конструкций
    • if-else для обработки ошибок
    • ранние возвраты
    • вложенные условия
    • прямой доступ к данным без монадической обработки

Проявление:
  if result.error:
    return default_value  # ранний возврат
  else:
    process(result.data)  # вложенное условие
```

**4. Сложность тестирования:**

```
Проблема ::=
  Для тестирования требуется
    • мокирование состояния класса
    • инициализация хранилища перед каждым тестом
    • очистка состояния после тестов
    • сложная настройка тестового окружения

Проявление:
  Тест → setup(инициализация_хранилища) → выполнение → cleanup(очистка_состояния)
```

### Проблемы композиции и расширяемости

**5. Отсутствие функциональной композиции:**

```
Проблема ::=
  Операции выполняются линейно
    • нельзя легко комбинировать функции
    • сложно добавить промежуточные шаги
    • нет механизма композиции операций

Проявление:
  operation1()
    → operation2()
      → operation3()  # линейная цепочка, сложно расширять
```

**6. Отсутствие явной обработки ошибок:**

```
Проблема ::=
  Ошибки обрабатываются через исключения
    • нет явного представления успеха/ошибки
    • сложно комбинировать операции с ошибками
    • поток данных неявный

Проявление:
  try:
    result = operation()
  except Exception as e:
    handle_error(e)  # императивная обработка
```

---

## Обзор изменений

Рефакторинг направлен на приведение кода к нормальному виду (normal form) в контексте функционального программирования. Основная цель - устранение императивных паттернов и замена их на функциональные абстракции.

**Основные направления рефакторинга:**

1. **Чистые функции**: Извлечение логики в чистые функции без побочных эффектов
2. **Монадическая обработка**: Обработка ошибок и optional значений через монады
3. **Иммутабельность**: Использование иммутабельных структур данных
4. **Функциональная композиция**: Композиция функций вместо линейных вызовов
5. **Устранение императивных паттернов**: Замена if-else, ранних возвратов на функциональные абстракции

---

## Часть I: Архитектура системы хранения данных

### 1.1 Изначальная архитектура (до рефакторинга)

#### Назначение системы хранения данных

Система хранения данных реализована на основе оперативной памяти. Основное назначение:

- **Быстрый доступ**: Все данные хранятся в оперативной памяти для мгновенного доступа
- **Разделение по типам**: Каждый тип данных хранится в отдельном экземпляре MemoryStorage
- **Эфемерность**: Данные существуют только во время работы приложения
- **Функциональный интерфейс**: Монадическая обработка операций через `StorageResult`

#### Структура данных в памяти

**Формальная структура оперативной памяти:**

```
ОперативнаяПамять ::= { MemoryStorage }

MemoryStorage ::= <экземпляр> • <данные>

где:
  <экземпляр> ::= users_storage | resume_storage | job_storage | analysis_storage | logs_storage
  
  <данные> ::= self._data: List[Dict[str, Any]]
    где:
      users_storage._data ::= List[Пользователь]
      resume_storage._data ::= List[Резюме]
      job_storage._data ::= List[Вакансия]
      analysis_storage._data ::= List[Анализ]
      logs_storage._data ::= List[Лог]
```

**Связи с модулями:**

```
Модуль ::= auth.py | main.py

MemoryStorage(users_storage) → auth.py
MemoryStorage(resume_storage) → main.py
MemoryStorage(jobs_storage) → main.py
MemoryStorage(analysis_storage) → main.py
MemoryStorage(logs_storage) → main.py
```

#### Связи между модулями и данными

**Архитектурные слои:**

```
Система ::= СлойХранения • СлойБизнесЛогики • СлойМоделей

СлойХранения ::= ОперативнаяПамять • MemoryStorage
  где:
    ОперативнаяПамять ::= { self._data: List[Dict] }
    MemoryStorage ::= класс <хранилище>

СлойБизнесЛогики ::= auth.py • main.py • rag_analyzer.py

СлойМоделей ::= models.py
```

**Связи (зависимости):**

```
MemoryStorage ──[in-memory]──> ОперативнаяПамять
MemoryStorage ──[users_storage]──> auth.py
MemoryStorage ──[resume_storage]──> main.py
MemoryStorage ──[analysis_storage]──> main.py
MemoryStorage ──[job_storage]──> main.py
MemoryStorage ──[logs_storage]──> main.py
main.py ──[использует]──> models.py
rag_analyzer.py ──[использует]──> models.py
main.py ──[вызывает]──> rag_analyzer.py
```

#### Поток данных при операциях

##### Чтение данных:

**Формальная спецификация потока:**

```
ЧтениеДанных ::= HTTPHandler → MemoryStorage → ОперативнаяПамять → StorageResult

детализация:
  HTTPHandler.read_all() 
    → MemoryStorage.read_all()
      → MemoryStorage._read_data()
        → self._data.copy()
          → ОперативнаяПамять.read()
            → List[Dict]
      → StorageResult(data=List[Dict])
    → StorageResult.fold(success_func, error_func)
      → HTTPHandler
```

**Нотация процесса:**

```
read_all() ::= 
  create(StorageOperation(action='read_all'))
    • execute_operation()
      • _read_data()
        • self._data.copy()
      • StorageResult(data=data)
    • fold(success_func, error_func)
```

##### Запись данных:

**Формальная спецификация потока:**

```
ЗаписьДанных ::= HTTPHandler → MemoryStorage → ОперативнаяПамять → StorageResult

детализация:
  HTTPHandler.add_item(item)
    → MemoryStorage.add_item(item)
      → enrich_item_with_metadata(item)
        → enriched_item
      → MemoryStorage._read_data()
        → self._data.copy()
          → existing_data
      → new_data = existing_data + [enriched_item]
      → MemoryStorage._write_data(new_data)
        → self._data = new_data.copy()
          → ОперативнаяПамять.write(new_data)
      → StorageResult(data=enriched_item['id'])
    → StorageResult.fold(success_func, error_func)
      → HTTPHandler
```

**Нотация процесса:**

```
add_item(item) ::=
  create(StorageOperation(action='add_item', data=item))
    • enrich_item_with_metadata(item)
    • execute_operation()
      • _read_data()
        • self._data.copy()
      • new_data = existing_data + [enriched_item]
      • _write_data(new_data)
        • self._data = new_data.copy()
      • StorageResult(data=item_id)
    • fold(success_func, error_func)
```

#### Методы и их связи

**Структура класса MemoryStorage (до рефакторинга):**

```
MemoryStorage ::= Инициализация • Операции • ПубличныеМетоды • ВспомогательныеФункции

Инициализация ::= 
  __init__(name: str = None)
    → self._data = []
    → self._name = name

Операции ::=
  execute_operation(operation: StorageOperation)
    → _read_data() | _write_data(data)
      → _read_data()
        → self._data.copy()
      → _write_data(data)
        → self._data = data.copy()

ПубличныеМетоды ::= 
  read_all() 
    → create(StorageOperation(action='read_all'))
    → execute_operation()
  
  add_item(item: Dict)
    → create(StorageOperation(action='add_item', data=item))
    → execute_operation()
      • enrich_item_with_metadata(item)
  
  get_item(item_id: str)
    → create(StorageOperation(action='get_item', item_id=item_id))
    → execute_operation()
      • Maybe(data).bind(...)
  
  update_item(item_id: str, updates: Dict)
    → create(StorageOperation(action='update_item', item_id=item_id, updates=updates))
    → execute_operation()
      • update_item_timestamp(updates)
  
  delete_item(item_id: str)
    → create(StorageOperation(action='delete_item', item_id=item_id))
    → execute_operation()
  
  find_items(filters: Dict)
    → create(StorageOperation(action='find_items', filters=filters))
    → execute_operation()
      • create_predicate_from_filters(filters)

ВспомогательныеФункции ::= 
  enrich_item_with_metadata(item: Dict) → Dict
  update_item_timestamp(updates: Dict) → Dict
  create_predicate_from_filters(filters: Dict) → Predicate
```

**Связи методов:**

```
__init__ → self._data = []

read_all → create(StorageOperation) → execute_operation → _read_data → self._data.copy
add_item → create(StorageOperation) → execute_operation → _read_data • _write_data • enrich_item_with_metadata
get_item → create(StorageOperation) → execute_operation → _read_data • Maybe
update_item → create(StorageOperation) → execute_operation → _read_data • _write_data • update_item_timestamp
delete_item → create(StorageOperation) → execute_operation → _read_data • _write_data
find_items → create(StorageOperation) → execute_operation → _read_data • create_predicate_from_filters
```

### 1.2 Новая архитектура (после рефакторинга)

#### Назначение улучшенной системы хранения

Система хранения данных улучшена с точки зрения функционального программирования:

- **Чистые функции**: Извлечение логики обработки данных в чистые функции
- **Монадическая обработка**: Сохранение и улучшение функционального интерфейса через монады
- **Иммутабельность**: Использование иммутабельных структур для операций
- **Эфемерность**: Данные существуют только во время работы приложения (без изменений)

#### Структура данных в памяти

**Формальная структура памяти:**

```
ОперативнаяПамять ::= { MemoryStorage }

MemoryStorage ::= <экземпляр> • <данные>

где:
  <экземпляр> ::= users_storage | resume_storage | job_storage | analysis_storage | logs_storage
  
  <данные> ::= self._data: List[Dict[str, Any]]
    где:
      users_storage._data ::= List[Пользователь]
      resume_storage._data ::= List[Резюме]
      job_storage._data ::= List[Вакансия]
      analysis_storage._data ::= List[Анализ]
      logs_storage._data ::= List[Лог]
```

**Связи с модулями:**

```
MemoryStorage(users_storage) → auth.py
MemoryStorage(resume_storage) → main.py
MemoryStorage(job_storage) → main.py
MemoryStorage(analysis_storage) → main.py
MemoryStorage(logs_storage) → main.py
```

#### Измененные связи между модулями

**Архитектурные слои (новая структура):**

```
Система ::= СлойХранения • СлойБизнесЛогики • СлойМоделей

СлойХранения ::= ОперативнаяПамять • MemoryStorage
  где:
    ОперативнаяПамять ::= { self._data: List[Dict] }
    MemoryStorage ::= класс <хранилище>

СлойБизнесЛогики ::= auth.py • main.py • rag_analyzer.py

СлойМоделей ::= models.py
```

**Связи (зависимости):**

```
MemoryStorage ──[in-memory]──> ОперативнаяПамять
MemoryStorage ──[users_storage]──> auth.py
MemoryStorage ──[resume_storage]──> main.py
MemoryStorage ──[analysis_storage]──> main.py
MemoryStorage ──[job_storage]──> main.py
MemoryStorage ──[logs_storage]──> main.py
main.py ──[использует]──> models.py
rag_analyzer.py ──[использует]──> models.py
main.py ──[вызывает]──> rag_analyzer.py
```

#### Новый поток данных при операциях

##### Чтение данных:

**Формальная спецификация потока:**

```
ЧтениеДанных ::= HTTPHandler → MemoryStorage → ОперативнаяПамять → StorageResult

детализация:
  HTTPHandler.read_all() 
    → MemoryStorage.read_all()
      → MemoryStorage._read_data()
        → self._data.copy()
          → ОперативнаяПамять.read()
            → List[Dict]
      → StorageResult(data=List[Dict])
    → StorageResult.fold(success_func, error_func)
      → HTTPHandler
```

**Нотация процесса:**

```
read_all() ::= 
  create(StorageOperation(action='read_all'))
    • execute_operation()
      • _read_data()
        • self._data.copy()
      • StorageResult(data=data)
    • fold(success_func, error_func)
```

##### Запись данных:

**Формальная спецификация потока:**

```
ЗаписьДанных ::= HTTPHandler → MemoryStorage → ОперативнаяПамять → StorageResult

детализация:
  HTTPHandler.add_item(item)
    → MemoryStorage.add_item(item)
      → enrich_item_with_metadata(item)
        → enriched_item
      → MemoryStorage._read_data()
        → self._data.copy()
          → existing_data
      → new_data = existing_data + [enriched_item]
      → MemoryStorage._write_data(new_data)
        → self._data = new_data.copy()
          → ОперативнаяПамять.write(new_data)
      → StorageResult(data=enriched_item['id'])
    → StorageResult.fold(success_func, error_func)
      → HTTPHandler
```

**Нотация процесса:**

```
add_item(item) ::=
  create(StorageOperation(action='add_item', data=item))
    • enrich_item_with_metadata(item)
    • execute_operation()
      • _read_data()
        • self._data.copy()
      • new_data = existing_data + [enriched_item]
      • _write_data(new_data)
        • self._data = new_data.copy()
      • StorageResult(data=item_id)
    • fold(success_func, error_func)
```

#### Измененные методы и связи

**Структура класса MemoryStorage:**

```
MemoryStorage ::= Инициализация • Операции • ПубличныеМетоды • МетодыСовместимости • ВспомогательныеФункции

Инициализация ::= 
  __init__(name: str = None)
    → self._data = []
    → self._name = name

Операции ::=
  execute_operation(operation: StorageOperation)
    → _read_data() | _write_data(data)
      → _read_data()
        → self._data.copy()
      → _write_data(data)
        → self._data = data.copy()

ПубличныеМетоды ::= 
  read_all() 
    → create(StorageOperation(action='read_all'))
    → execute_operation()
  
  add_item(item: Dict)
    → create(StorageOperation(action='add_item', data=item))
    → execute_operation()
      • enrich_item_with_metadata(item)
  
  get_item(item_id: str)
    → create(StorageOperation(action='get_item', item_id=item_id))
    → execute_operation()
      • Maybe(data).bind(...)
  
  update_item(item_id: str, updates: Dict)
    → create(StorageOperation(action='update_item', item_id=item_id, updates=updates))
    → execute_operation()
      • update_item_timestamp(updates)
  
  delete_item(item_id: str)
    → create(StorageOperation(action='delete_item', item_id=item_id))
    → execute_operation()
  
  find_items(filters: Dict)
    → create(StorageOperation(action='find_items', filters=filters))
    → execute_operation()
      • create_predicate_from_filters(filters)

МетодыСовместимости ::=
  write_all(data: StorageData)
    → _write_data(data)
    → StorageResult(data=True)
  
  load() → Dict[str, Any]
    → _read_data()
    → transform_to_dict(data)
      → { item['id']: item for item in data }

ВспомогательныеФункции ::= 
  enrich_item_with_metadata(item: Dict) → Dict
  update_item_timestamp(updates: Dict) → Dict
  create_predicate_from_filters(filters: Dict) → Predicate
```

**Связи методов:**

```
__init__ → self._data = []

read_all → create(StorageOperation) → execute_operation → _read_data → self._data.copy
add_item → create(StorageOperation) → execute_operation → _read_data • _write_data • enrich_item_with_metadata
get_item → create(StorageOperation) → execute_operation → _read_data • Maybe
update_item → create(StorageOperation) → execute_operation → _read_data • _write_data • update_item_timestamp
delete_item → create(StorageOperation) → execute_operation → _read_data • _write_data
find_items → create(StorageOperation) → execute_operation → _read_data • create_predicate_from_filters

write_all → _write_data → self._data = data.copy
load → _read_data → transform_to_dict
```

### 1.3 Сравнение архитектур

**ДО: Императивный подход с побочными эффектами**

```
ЧтениеДанных_ДО ::=
  HTTPRequest 
    → read_all()
    → MemoryStorage
      → self._data (прямой доступ к состоянию)
      → return self._data (без монадической обработки)
        → StorageResult
```

**ПОСЛЕ: Функциональный подход с монадами**

```
ЧтениеДанных_ПОСЛЕ ::=
  HTTPRequest
    → read_all()
    → MemoryStorage
      → self._data.copy() (иммутабельная копия)
      → StorageResult(data=data) (монадическая обертка)
        → fold(success_func, error_func) (функциональная обработка)
          → StorageResult
```

**Сравнительная таблица операций:**

| Операция | ДО (Императивный стиль) | ПОСЛЕ (Функциональный стиль) |
|----------|------------------------|----------------------------|
| `read_all()` | self._data → return | self._data.copy() → StorageResult → fold() |
| `add_item()` | modify → assign | copy → enrich → copy → assign → StorageResult → fold() |
| `get_item()` | find → return | copy → Maybe → StorageResult → fold() |
| `update_item()` | modify → assign | copy → update → copy → assign → StorageResult → fold() |
| `delete_item()` | filter → assign | copy → filter → copy → assign → StorageResult → fold() |

---

## Часть II: Применение техник к коду

### 2.1 Техника 1: ЭКСТРАКЦИЯ ЧИСТЫХ ФУНКЦИЙ (Pure Function Extraction)

#### Назначение кода до рефакторинга

**Методы класса `MemoryStorage`:**

```
MemoryStorage._read_data() ::=
  асинхронная операция
    • зависимость: self._data (состояние класса)
    • побочный_эффект: обращение к изменяемому состоянию
    • возврат: List[Dict]

MemoryStorage._write_data(data) ::=
  асинхронная операция
    • зависимость: self._data (состояние класса)
    • побочный_эффект: мутация self._data
    • возврат: None

MemoryStorage.enrich_item_with_metadata() ::=
  метод класса (должен быть чистой функцией)
    • зависит от generate_item_id() и get_current_timestamp()
    • смешан с операциями состояния
```

**Связи:**

```
Метод → зависит_от(self._data) → побочный_эффект(мутация_состояния)
ЧистыеФункции → смешаны_с(методами_состояния)
ОбработкаОшибок → встроена_в(методы)
```

#### Применение техники

**Извлечение чистых функций:**

**ДО: Методы класса со смешанной логикой**

```
MemoryStorage._read_data() ::=
  self._data (зависимость от состояния)
    → return self._data (прямой доступ)

MemoryStorage.enrich_item_with_metadata(item) ::=
  метод в классе (смешан с операциями состояния)
    → generate_item_id()
    → get_current_timestamp()
    → { item, 'id', 'created_at', 'updated_at' }
```

**ПОСЛЕ: Разделение чистых функций и методов**

```
MemoryStorage._read_data() ::=
  self._data.copy() (чистая операция - возвращает копию)
    → результат

enrich_item_with_metadata(item: Dict) → Dict ::=
  чистая функция (извлечена из класса)
    • generate_item_id() (чистая функция)
    • get_current_timestamp() (чистая функция)
    • { item, 'id', 'created_at', 'updated_at' } (чистая трансформация)

update_item_timestamp(updates: Dict) → Dict ::=
  чистая функция (извлечена из класса)
    • get_current_timestamp() (чистая функция)
    • { updates, 'updated_at' } (чистая трансформация)

create_predicate_from_filters(filters: Dict) → Predicate ::=
  чистая функция (извлечена из класса)
    • lambda item: all(item.get(key) == value for key, value in filters.items())
```

**Результат:**
- `_read_data()`: Теперь возвращает копию `self._data` (иммутабельная операция)
- `_write_data()`: Теперь присваивает `self._data = data.copy()` (безопасное копирование)
- Вспомогательные функции извлечены из класса и стали чистыми функциями
- Чистая логика отделена от операций с состоянием

### 2.2 Техника 2: УЛУЧШЕНИЕ ОБРАБОТКИ ДАННЫХ

#### Назначение улучшаемых компонентов

**Методы, которые были улучшены:**

```
_read_data() ::= УЛУЧШЕН
  ДО: → return self._data (прямой доступ к состоянию)
  ПОСЛЕ: → return self._data.copy() (иммутабельная копия)

_write_data() ::= УЛУЧШЕН
  ДО: → self._data = data (прямое присваивание)
  ПОСЛЕ: → self._data = data.copy() (копирование для безопасности)

enrich_item_with_metadata() ::= ИЗВЛЕЧЕНА
  ДО: → метод класса (смешан с операциями состояния)
  ПОСЛЕ: → чистая функция на уровне модуля
```

#### Применение техники

**Трансформация методов:**

**Метод _read_data:**

```
_read_data() ::=
  ДО (Императивный стиль):
    return self._data  # прямой доступ к изменяемому состоянию

  ПОСЛЕ (Функциональный стиль):
    return self._data.copy()  # иммутабельная копия
```

**Метод _write_data:**

```
_write_data(data) ::=
  ДО (Императивный стиль):
    self._data = data  # прямое присваивание

  ПОСЛЕ (Функциональный стиль):
    self._data = data.copy()  # копирование для предотвращения неожиданных мутаций
```

**Функция enrich_item_with_metadata:**

```
enrich_item_with_metadata() ::=
  ДО:
    метод класса MemoryStorage
      • смешан с операциями состояния
      • сложно тестировать

  ПОСЛЕ:
    чистая функция на уровне модуля
      • не зависит от состояния
      • легко тестировать
      • может быть переиспользована
```

### 2.3 Техника 3: СОХРАНЕНИЕ ФУНКЦИОНАЛЬНОГО ИНТЕРФЕЙСА

#### Назначение обратной совместимости

**Проблема:** Модули `main.py` и `auth.py` используют `JSONStorage` как алиас для `MemoryStorage`.

**Решение:** Алиасы для обратной совместимости

```
Алиасы ::=
  JSONStorage ::= MemoryStorage
  JSONStorageFP ::= MemoryStorage

где:
  MemoryStorage ::= основной_класс
    • __init__(name: str = None)
    • _read_data() → StorageData
    • _write_data(data: StorageData) → None
```

**Использование:**

```
main.py ::=
  from storage import JSONStorage
  
  resume_storage ::= JSONStorage("resumes")
    → MemoryStorage("resumes")  # имя игнорируется, для совместимости
  
  analysis_storage ::= JSONStorage("analyses")
    → MemoryStorage("analyses")
  
  job_storage ::= JSONStorage("jobs")
    → MemoryStorage("jobs")
  
  logs_storage ::= JSONStorage("logs")
    → MemoryStorage("logs")

auth.py ::=
  from storage import JSONStorage
  
  users_storage ::= JSONStorage("users")
    → MemoryStorage("users")
```

**Методы совместимости:**

```
write_all(data: StorageData) → StorageResult ::=
  _write_data(data)
    → StorageResult(data=True)

load() → Dict[str, Any] ::=
  _read_data()
    → transform_to_dict(data)
      → { item.get('id', str(i)): item for i, item in enumerate(data) }
```

**Использование в auth.py:**

```
create_admin_user(username, password) ::=
  users_storage.read_all()
    → users_storage.write_all(new_users)
      → write_all(data)
        → _write_data(data)

promote_to_admin(username) ::=
  users_storage.read_all()
    → users_storage.write_all(updated_users)
      → write_all(data)
        → _write_data(data)

get_current_user(request) ::=
  users_storage.read_all()
    → load() [используется в fallback]
      → _read_data()
        → transform_to_dict()
```

### 2.4 Техника 4: МОНАДИЧЕСКАЯ ОБРАБОТКА ОШИБОК (сохранена)

#### Назначение монадической обработки

**До и после рефакторинга монадическая обработка осталась неизменной:**

```
МонадическиеСтруктуры ::=
  StorageOperation
    • action: str
    • data: Optional[Any]
    • filters: Optional[Dict]
    • item_id: Optional[str]
    • updates: Optional[Dict]
  
  StorageResult
    • data: Optional[Any]
    • success: bool
    • error: Optional[Exception]
    • методы: map, bind, fold
```

**Использование в MemoryStorage:**

```
MemoryStorage.execute_operation(operation) ::=
  → StorageResult(data=..., success=..., error=...)

MemoryStorage.read_all() ::=
  → StorageResult(data=List[Dict])

MemoryStorage.add_item(item) ::=
  → StorageResult(data=item_id)

MemoryStorage.get_item(item_id) ::=
  → StorageResult(data=Dict | None)

MemoryStorage.update_item(item_id, updates) ::=
  → StorageResult(data=bool)

MemoryStorage.delete_item(item_id) ::=
  → StorageResult(data=bool)
```

**Использование в handlers:**

```
main.py handlers ::=
  resume_storage.read_all()
    → StorageResult.fold(success_func, error_func)
  resume_storage.add_item(item)
    → StorageResult.fold(success_func, error_func)
  resume_storage.get_item(id)
    → StorageResult.fold(success_func, error_func)

auth.py handlers ::=
  users_storage.read_all()
    → StorageResult.fold(success_func, error_func)
  users_storage.add_item(item)
    → StorageResult.fold(success_func, error_func)
```

#### Поток монадических операций

**Чтение:**

```
read_all() ::=
  Handler
    → MemoryStorage.read_all()
      → StorageResult(data=self._data.copy())
        → fold(success_func, error_func)
          → Handler
```

**Добавление:**

```
add_item(item) ::=
  Handler
    → MemoryStorage.add_item(item)
      → enrich_item_with_metadata(item)
      → StorageResult(data=item_id)
        → fold(success_func, error_func)
          → Handler
```

**Получение:**

```
get_item(id) ::=
  Handler
    → MemoryStorage.get_item(id)
      → Maybe(data).bind(lambda d: Maybe(next(...)))
        → Maybe(item)
      → StorageResult(data=item)
        → fold(success_func, error_func)
          → Handler
```

---

## Часть III: Детальное описание изменений

### 3.1 ЭКСТРАКЦИЯ ЧИСТЫХ ФУНКЦИЙ (Pure Function Extraction)

### Было (Императивный стиль):
```python
class JSONStorageFP:
    def _calculate_mock_analysis(self, resume, job_description):
        # Метод класса с зависимостью от self
        skills_match = len(set(resume.skills) & set(job_description.skills_required))
        # ... логика внутри класса
```

### Стало (Функциональный стиль):
```python
# Чистая функция на уровне модуля
def calculate_mock_analysis(resume: Resume, job_description: JobDescription) -> AnalysisData:
    """Чистая функция расчета мок-анализа"""
    skills_match = len(set(resume.skills) & set(job_description.skills_required))
    # ... изолированная логика без состояния
```

**Принципы ФП:**
- ✅ **Чистота функций**: нет побочных эффектов, результат зависит только от входных данных
- ✅ **Референциальная прозрачность**: функция может быть заменена своим результатом
- ✅ **Тестируемость**: легко тестировать без мокирования класса

**Извлеченные чистые функции:**
1. `prepare_analysis_context()` - подготовка контекста
2. `create_analysis_prompt()` - создание промпта
3. `calculate_mock_analysis()` - расчет мок-анализа
4. `get_default_analysis()` - анализ по умолчанию
5. `create_analysis_result_from_data()` - создание результата
6. `create_mock_analysis_result()` - создание мок-результата
7. `parse_response_safe()` - безопасный парсинг

---

### 3.2 МОНАДИЧЕСКАЯ ОБРАБОТКА ОШИБОК (Monadic Error Handling)

### Было (Императивный стиль):
```python
async def analyze_resume_relevance(self, resume, job_description):
    # Подготовка контекста
    context_result = await self._prepare_context(...)
    if context_result.error:  # ❌ Императивная проверка
        return self._create_mock_analysis(...)
    
    # Анализ
    analysis_result = await self._analyze_with_rag(context_result)
    if analysis_result.error:  # ❌ Императивная проверка
        return self._create_mock_analysis(...)
    
    # Создание результата
    final_result = self._create_analysis_result(analysis_result)
    if final_result.error:  # ❌ Императивная проверка
        return self._create_mock_analysis(...)
```

### Стало (Монадический стиль):
```python
async def analyze_resume_relevance(self, resume, job_description):
    # Функциональный pipeline через монадические операции
    initial_result = await self._prepare_context_safe(...)
    analysis_result = await self._analyze_with_rag_safe(initial_result)
    final_result = await self._create_analysis_result_safe(analysis_result)
    
    # ✅ Catamorphism (fold) для извлечения результата
    return final_result.fold(
        success_func=lambda result: result,
        error_func=lambda e: self._handle_error(e, resume, job_description)
    )
```

**Принципы ФП:**
- ✅ **Either-монада**: `AnalysisResultM` представляет успех или ошибку
- ✅ **Catamorphism**: `fold` - универсальный способ извлечения результата
- ✅ **Композиция**: pipeline из монадических операций без промежуточных проверок
- ✅ **Отсутствие ранних возвратов**: ошибки "пропускаются" через pipeline до `fold`

**Добавленные монадические операции:**
- `bind_async()` - асинхронный bind для цепочки операций
- `fold()` - catamorphism для извлечения результата
- `map()` - functor map для преобразования значений

---

### 3.3 ИММУТАБЕЛЬНОСТЬ (Immutability)

### Было (Мутабельный стиль):
```python
# Потенциальная мутация контекста
updated_context = AnalysisContext(
    **{**result.context.__dict__, "parsed_data": analysis_data}
)
```

### Стало (Иммутабельный стиль):
```python
# Явное создание нового объекта (frozen dataclass)
updated_context = AnalysisContext(
    resume=result.context.resume,
    job_description=result.context.job_description,
    context_text=result.context.context_text,
    prompt=result.context.prompt,
    parsed_data=analysis_data  # ✅ Новое значение
)
```

**Принципы ФП:**
- ✅ **Frozen dataclass**: `@dataclass(frozen=True)` гарантирует иммутабельность
- ✅ **Value semantics**: каждый "изменение" создает новый объект
- ✅ **Отсутствие побочных эффектов**: нет неожиданных мутаций

---

### 3.4 ФУНКЦИОНАЛЬНАЯ КОМПОЗИЦИЯ (Function Composition)

### Добавлено:
```python
# Композиция синхронных функций
def compose(*functions: Callable) -> Callable:
    """Композиция функций"""
    return reduce(lambda f, g: lambda x: g(f(x)), functions)

# Композиция асинхронных функций
async def async_compose(*functions: Callable[[T], Awaitable[U]]) -> Callable[[T], Awaitable[U]]:
    """Композиция асинхронных функций"""
    async def composed(x: T) -> U:
        result = x
        for func in functions:
            result = await func(result)
        return result
    return composed
```

**Принципы ФП:**
- ✅ **Композиция как первоклассная операция**: функции можно комбинировать
- ✅ **Reduce для композиции**: использование `reduce` для построения цепочки
- ✅ **Асинхронная композиция**: поддержка async/await в композиции

---

### 3.5 MAYBE МОНАДА ДЛЯ OPTIONAL ЗНАЧЕНИЙ

### Улучшено использование:
```python
# Функциональная цепочка через Maybe монаду
api_response_maybe = await self._call_openai_api_safe(prompt)
parse_result = parse_response_safe(api_response_maybe.value)
analysis_data = parse_result.or_else(get_default_analysis())
```

**Принципы ФП:**
- ✅ **Maybe монада**: безопасная обработка `None` значений
- ✅ **`or_else`**: функциональная альтернатива `if-else` для fallback
- ✅ **Композиция через `bind`**: цепочка операций с автоматической обработкой `None`

---

### 3.6 УСТРАНЕНИЕ ИМПЕРАТИВНЫХ ПАТТЕРНОВ

### Паттерн 1: Ранние возвраты (Early Returns)

**Было:**
```python
if context_result.error:
    return self._create_mock_analysis(...)  # ❌ Ранний возврат
```

**Стало:**
```python
# ✅ Ошибка "пропускается" через pipeline до fold
return final_result.fold(
    success_func=lambda result: result,
    error_func=lambda e: self._handle_error(...)
)
```

### Паттерн 2: Вложенные if-ы (Nested Conditionals)

**Было:**
```python
if api_result.value is None:
    analysis_data = self._get_default_analysis()
else:
    parse_result = self._parse_response_safe(api_result.value)
    analysis_data = parse_result.or_else(self._get_default_analysis())
```

**Стало:**
```python
# ✅ Функциональная цепочка через Maybe
api_response_maybe = await self._call_openai_api_safe(prompt)
parse_result = parse_response_safe(api_response_maybe.value)
analysis_data = parse_result.or_else(get_default_analysis())
```

---

### 3.7 НОРМАЛЬНАЯ ФОРМА (Normal Form)

### Определение нормальной формы в контексте ФП:
Код находится в нормальной форме, если:
1. ✅ Все функции чистые (где возможно)
2. ✅ Побочные эффекты изолированы и явно обозначены
3. ✅ Ошибки обрабатываются через монады, а не через исключения
4. ✅ Данные иммутабельны
5. ✅ Композиция функций используется вместо вложенных вызовов

### Текущее состояние:
- ✅ **Чистые функции**: все вычисления вынесены в чистые функции
- ✅ **Монадическая обработка**: ошибки через `AnalysisResultM` и `Maybe`
- ✅ **Иммутабельность**: `AnalysisContext` - frozen dataclass
- ✅ **Композиция**: функции можно комбинировать
- ⚠️ **Побочные эффекты**: логирование и API вызовы изолированы, но присутствуют (необходимо для практических целей)

---

### 3.8 СРАВНИТЕЛЬНАЯ ТАБЛИЦА

| Аспект | До рефакторинга | После рефакторинга |
|--------|----------------|-------------------|
| **Обработка ошибок** | Императивные `if-else` | Монадический `fold` |
| **Чистота функций** | Методы класса | Изолированные чистые функции |
| **Иммутабельность** | Потенциальные мутации | Frozen dataclass |
| **Композиция** | Линейные вызовы | `compose` / `async_compose` |
| **Optional значения** | Проверки на `None` | Maybe монада |
| **Ранние возвраты** | Множественные `return` | Единый `fold` в конце |
| **Тестируемость** | Требует мокирования класса | Чистые функции легко тестировать |
| **Хранение данных** | Оперативная память (императивный доступ) | Оперативная память (функциональный доступ) |
| **Зависимости** | Стандартная библиотека | Стандартная библиотека |

---

### 3.9 ПРЕИМУЩЕСТВА РЕФАКТОРИНГА

### С точки зрения функционального программирования:

1. **Референциальная прозрачность**
   - Чистые функции можно заменять их результатами
   - Упрощает рассуждения о программе

2. **Композируемость**
   - Функции можно комбинировать в pipeline
   - Легко добавлять новые шаги

3. **Предсказуемость**
   - Иммутабельные данные исключают неожиданные мутации
   - Монадическая обработка ошибок делает поток данных явным

4. **Тестируемость**
   - Чистые функции легко тестировать
   - Не требуют мокирования состояния

5. **Расширяемость**
   - Новые шаги pipeline добавляются через композицию
   - Не нужно изменять существующий код

6. **Производительность**
   - Хранение в памяти устраняет I/O операции
   - Мгновенный доступ к данным

7. **Упрощение**
   - Чистые функции легче понимать и поддерживать
   - Меньше побочных эффектов

---

### 3.10 ОСТАВШИЕСЯ ИМПЕРАТИВНЫЕ ЭЛЕМЕНТЫ

Некоторые императивные элементы остались по практическим причинам:

1. **Логирование** - побочный эффект, но необходим для отладки
2. **API вызовы** - побочные эффекты, но изолированы в отдельных функциях
3. **Генерация UUID** - побочный эффект, но необходим для уникальности
4. **Мутация `self._data`** - необходимо для хранения состояния в памяти

Эти элементы изолированы и не влияют на чистоту основной логики.

---

## Заключение

Рефакторинг привел код к нормальной форме в контексте функционального программирования:
- ✅ Чистые функции для вычислений
- ✅ Монадическая обработка ошибок
- ✅ Иммутабельные структуры данных
- ✅ Функциональная композиция
- ✅ Отсутствие ранних возвратов и вложенных условий
- ✅ Улучшенная обработка данных в оперативной памяти
- ✅ Разделение чистых функций и операций с состоянием

Код стал более декларативным, композируемым и предсказуемым, сохраняя при этом практичность для реальных задач.
