---
name: add-django-api
description: Создание нового API эндпоинта в Django REST Framework. Используй при добавлении view, serializer, service, manager или нового метода API.
---

# Создание нового API эндпоинта

## When to Use

Используй этот skill когда:
- Добавляешь новый эндпоинт API
- Создаёшь view, serializer, service или manager
- Добавляешь новое право доступа (action)
- Выносишь сложные запросы в managers

## Instructions

### Архитектура

```
urls.py → views.py → serializers.py → services.py
                                           ↓
                          models.py ← managers.py
```

### 1. Добавь URL

```python
# urls.py
path("<int:terminal_pk>/my_action/", MyNewView.as_view(), name="my_action"),
```

### 2. Создай View и Serializer

```python
# views.py
from common.permissions import TerminalActionBasedPermission
from common.views import TerminalClientContextAPIView

class MyNewView(TerminalClientContextAPIView):
    permission_classes = [TerminalActionBasedPermission]
    required_actions = ['container_edit']
    queryset = Container.objects.none()
    serializer_class = CustomSerializer

# serializers.py
class CustomSerlizer(serilizers.ModelSerializer / serializers.Serilizer):
    field1 = serilizers.PrimaryKey(queryset=CustomModel.objects.all())
    field2 = serilizers.MethodFieldSerializer(...)
    
    class Meta:
        model = CustomModel
        fields = '__all__'
    
    def update(self, validation_data, *args, **kwargs):
        ...
        custom_service = CustomService()
        result = custom_service.custom_update(validation_date)
        ...

    def create(self, validation_data, *args, **kwargs):
        ...
        custom_service = CustomService()
        result = custom_service.custom_create(validation_date)
        ...


```

### 3. Создай Service

Выноси бизнес-логику в `services.py`:

```python
# services.py
from common.services import BasicService
from rest_framework.exceptions import ValidationError, NotFound

class MyService(BasicService):
    @staticmethod
    def my_action(data: dict, terminal_id: int, user) -> dict:
        container_id = data.get('container_id')
        if not container_id:
            raise ValidationError("Контейнер обязателен")
        
        with transaction.atomic():
            container = Container.objects.select_for_update().get(pk=container_id)
            container.some_field = data.get('value')
            container.save()
        
        return {"status": "success", "container_id": container.pk}
```

### 4. Добавь права доступа

**Через атрибуты класса:**
```python
required_actions = ['container_edit']
```

**Через декоратор (разные права на методы):**
```python
from common.permissions import action_permission_required

@action_permission_required(permission_class=TerminalActionBasedPermission, required_action='container_view')
def get(self, request, *args, **kwargs): ...
```

**Новый action — добавь в `common/action_constants.py`:**
```python
MY_NEW_ACTION = 'my_new_action', 'Описание действия', 'Группа'
```

### 5. Вынеси сложные запросы в Manager

```python
# managers.py
class ContainerQuerySet(models.QuerySet):
    def gate_out_available(self):
        return self.filter(status=ContainerStatusConstant.ACCEPTED, is_blocked=False)
    
    def with_client_tariffs(self, client, terminal=None):
        tariff_filter = {'client': client, 'is_active': True, 'service_id': OuterRef('pk')}
        return self.annotate(
            client_price=Case(
                When(pk__in=ClientTariff.objects.filter(**tariff_filter).values('service_id'),
                     then=Subquery(ClientTariff.objects.filter(**tariff_filter).values('price')[:1])),
                default=F('base_price'),
            )
        )

class ContainerManager(models.Manager):
    def get_queryset(self) -> ContainerQuerySet:
        return ContainerQuerySet(self.model, using=self._db)
```

### 6. Обрабатывай ошибки

```python
# В services.py — выбрасывай исключения
raise ValidationError("Контейнер обязателен")  # 400
raise NotFound("Контейнер не найден")  # 404
raise ContainerIncorrectStatus("Неверный статус")  # 400, кастомное

# В views.py — пробрасывай
except Exception as e:
    raise e
```

**Кастомные исключения (`exceptions.py`):**
```python
from rest_framework.exceptions import APIException

class ContainerIncorrectStatus(APIException):
    status_code = 400
    default_detail = 'Контейнер недоступен'
    default_code = 'INVALID_STATUS'
```

## Examples

### ✅ Правильно: логика в service

```python
# views.py
def post(self, request, terminal_pk: int) -> Response:
    result = MyService.my_action(data=request.data, terminal_id=terminal_pk)
    return Response(result, status=status.HTTP_200_OK)

# services.py
class MyService(BasicService):
    @staticmethod
    def my_action(data: dict, terminal_id: int) -> dict:
        # Вся логика здесь
        with transaction.atomic():
            ...
```

### ❌ Неправильно: логика во view

```python
# views.py
def post(self, request, terminal_pk: int) -> Response:
    container = Container.objects.get(pk=request.data['container_id'])
    container.status = 2
    container.save()
    EntryPass.objects.create(...)  # Логика размазана по view
```

### ✅ Правильно: сложные запросы в manager

```python
# managers.py
def gate_out_available(self):
    return self.filter(status=2, is_blocked=False).exclude(...)

# views.py
containers = Container.objects.gate_out_available()
```

### ❌ Неправильно: сложные запросы в view/service

```python
# views.py
containers = Container.objects.filter(
    status=2, is_blocked=False
).annotate(
    has_report=Exists(...)
).exclude(...)  # Сложная логика не переиспользуется
```

### ✅ Правильно: права через атрибуты

```python
class MyView(TerminalClientContextAPIView):
    permission_classes = [TerminalActionBasedPermission]
    required_actions = ['container_edit']
```

### ❌ Неправильно: проверка прав вручную

```python
def post(self, request, ...):
    if not request.user.has_perm('container_edit'):  # Не используй вручную
        raise PermissionDenied()
```

### ✅ Правильно: транзакция с блокировкой

```python
with transaction.atomic():
    container = Container.objects.select_for_update().get(pk=id)
    container.status = new_status
    container.save()
```

### ❌ Неправильно: изменения без транзакции

```python
container = Container.objects.get(pk=id)
container.status = new_status
container.save()
entry_pass = EntryPass.objects.create(...)  # Race condition
```

## Безопасность: terminal_pk в URL — полный паттерн

### Когда добавлять `terminal_pk` в URL

Добавляй `terminal_pk` в URL если endpoint работает с **единственным объектом по ID** (retrieve / update / delete), и объект **напрямую связан с терминалом** (`model.terminal_id` существует как FK).

```
Объект имеет прямой terminal FK?
├── Да → добавить terminal_pk в URL
│        → get_object_or_404(Model, pk=object_pk, terminal_id=terminal_pk)
└── Нет (связь через relations: order__terminal, container__terminal)
         → использовать QuerysetByAccessibleTerminalsMixin
           с terminal_field_id_in='order__terminal_id__in'
```

Для **list-эндпоинтов** и **create** без ID в URL — `QuerysetByAccessibleTerminalsMixin` достаточно.

---

### Бэкенд: полный паттерн с `terminal_pk`

**urls.py:**
```python
path("<int:terminal_pk>/<int:object_pk>/", MyView.as_view(), name="my-view"),
```

**views.py:**
```python
from django.shortcuts import get_object_or_404
from common.permissions import TerminalActionBasedPermission

class MyView(APIView):
    permission_classes = [TerminalActionBasedPermission]
    required_actions = ['my_action']

    def get(self, request, terminal_pk, object_pk, *args, **kwargs):
        # TerminalActionBasedPermission уже проверил доступ к terminal_pk → 403 если нет
        obj = get_object_or_404(MyModel, pk=object_pk, terminal_id=terminal_pk, deleted=False)
        return Response(MySerializer(obj).data)
```

`TerminalActionBasedPermission` автоматически вызывает `_get_user_terminal(user, terminal_pk)` — если терминал недоступен, 403 срабатывает **до** попытки обратиться к объекту. Дополнительная ручная проверка не нужна.

---

### Бэкенд: `terminal` в body без `terminal_pk` в URL

```python
path("create/", MyCreateView.as_view())  # terminal_pk не в URL
```

`TerminalActionBasedPermission` проверяет только, есть ли у пользователя **хотя бы один** терминал с нужным action. `terminal` из body **не проверяется**. Нужна явная валидация в serializer:

```python
def validate_terminal(self, value):
    user = self.context['request'].user
    accessible = UserTerminal.objects.filter(
        user=user, terminal=value, deleted=False
    ).exists()
    if not accessible:
        raise ValidationError("Терминал недоступен.")
    return value
```

---

### Фронтенд: что менять при добавлении `terminal_pk` в URL

Когда бэкенд добавляет `terminal_pk` в URL endpoint-а, нужно обновить **всю цепочку** на фронте.

**1. API-слой (`store/newApi/` или `api/`):**
```js
// было
getMyObject: (objectId) => ({ url: `/api/myobjects/${objectId}/` })

// стало
getMyObject: ({ terminalId, objectId }) => ({ url: `/api/myobjects/${terminalId}/${objectId}/` })
```

**2. Хук (`entities/*/hooks/`):**
```ts
// было
export const useGetMyObject = (objectId: string) => {
  const [trigger, result] = useGetMyObjectQuery(objectId);
  ...
};

// стало
export const useGetMyObject = (terminalId: number | undefined, objectId: string) => {
  const [trigger, result] = useGetMyObjectQuery(
    terminalId && objectId ? { terminalId, objectId } : skipToken
  );
  ...
};
```

**3. Компонент — прокинуть `terminalId` через пропсы:**
```tsx
// источник данных (список, таблица) должен передавать terminalId
onClick={() => onItemClick(item.id, item.terminal?.id)}

// модал / форма получает terminalId
<MyModal terminalId={terminalId} objectId={objectId} />
```

**4. Роутинг — обновить URL страницы (если объект открывается отдельной страницей):**
```js
// shared/.../pageUrls.js
export const LINK_MY_OBJECT = (terminalId, objectId) =>
  `/${getRoleUrlPath()}/myobject/view/${terminalId}/${objectId}`;
```

```jsx
// App.jsx — добавить :terminalId в path
<Route path="myobject/view/:terminalId/:objectId" element={<MyObjectPage />} />
```

```jsx
// RequireAuth.jsx — добавить в оба whitelist-а (allowedRoutesForEmployee и allowedRoutesForClient)
`/accountEmpl/myobject/view/${terminalId}/${entryId}`,
`/accountClient/myobject/view/${terminalId}/${entryId}`,
```

> **Важно:** если новый URL имеет то же количество динамических сегментов что и существующий, добавь литеральный сегмент (`view`, `detail` и т.п.), чтобы избежать конфликта роутов React Router.

---

### Чеклист `terminal_pk` end-to-end

**Бэкенд:**
- [ ] `terminal_pk` добавлен в `path(...)` в `urls.py`
- [ ] View принимает `terminal_pk` как параметр метода
- [ ] `get_object_or_404(Model, pk=object_pk, terminal_id=terminal_pk)` вместо голого `get_object_or_404(Model, pk=object_pk)`
- [ ] `permission_classes = [TerminalActionBasedPermission]` + `required_actions` заданы

**Фронтенд:**
- [ ] URL в API-слое обновлён — `terminalId` включён в path
- [ ] Хук принимает `terminalId` и пропускает запрос (`skipToken`) если `terminalId` отсутствует
- [ ] `terminalId` прокинут из источника данных (список/таблица) через все компоненты до хука
- [ ] Если есть URL-страница: `pageUrls.js` обновлён, `App.jsx` роут обновлён
- [ ] `RequireAuth.jsx`: новый URL добавлен в оба whitelist-а (`allowedRoutesForEmployee` и `allowedRoutesForClient`)

## Checklist

### Создание эндпоинта
- [ ] URL добавлен в `urls.py`
- [ ] View создан с `permission_classes` и `required_actions`
- [ ] View импортирован в `urls.py`

### Права доступа
- [ ] Указан `required_actions` во View
- [ ] Новый action добавлен в `common/action_constants.py` (если требуется)
- [ ] Модуль терминала указан в `required_terminal_module` (если требуется)

### Логика
- [ ] Бизнес-логика вынесена в `services.py`
- [ ] Сложные QuerySet-методы вынесены в `managers.py`
- [ ] Валидация входных данных в `serializers.py`

### Ошибки и транзакции
- [ ] Ошибки через `ValidationError`, `NotFound`, кастомные исключения
- [ ] `transaction.atomic()` для нескольких изменений
- [ ] `select_for_update()` при конкурентном доступе

### Базовые классы View

| Класс | Когда использовать |
|-------|-------------------|
| `TerminalClientContextAPIView` | Контекст терминала и клиента |
| `APIView` | Простой эндпоинт |
| `generics.GenericAPIView` | CRUD с сериализатором |
| `QuerysetByAccessibleTerminalsMixin` | Фильтрация по терминалам пользователя |