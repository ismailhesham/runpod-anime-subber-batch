# runpod-anime-subber-batch — أداة الدفعات

دفعات من 10 حلقات: تحميل، ترجمة جاهزة من miraianime (أو DeepSeek لو مفيش)، حرق، رفع، مسح الدفعة، وتقف لحد ما تدوس الدفعة التالية.

الريبو ده مستقل تماماً. مفيش أي ربط بينه وبين أداة تانية.

## أول مرة على بود جديد (في الـ Web Terminal)
```
cd /workspace && git clone https://github.com/ismailhesham/runpod-anime-subber-batch.git && cd runpod-anime-subber-batch && bash setup.sh
```

## تحديث وإعادة تشغيل
```
cd /workspace/runpod-anime-subber-batch && git fetch origin && git reset --hard origin/main && bash run.sh
```

بعدها افتح الواجهة من RunPod: Connect ← HTTP Service (بورت 7860).

المفاتيح (DeepSeek / DoodStream) مش في الريبو: بتتحط من خانة الإعدادات في الواجهة وتتحفظ في `/workspace/subber_secrets.json`، أو من متغيرات البيئة `DEEPSEEK_API_KEY` و`DOODSTREAM_API_KEY`.
