from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('ai', '0001_initial_ai_models'),
    ]
    
    operations = [
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector"
        ),
        migrations.RunSQL(
            """
            CREATE INDEX ai_pe_combined_hnsw 
            ON ai_productembedding 
            USING hnsw (combined_vector vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """,
            reverse_sql="DROP INDEX IF EXISTS ai_pe_combined_hnsw"
        ),
        migrations.RunSQL(
            """
            CREATE INDEX ai_pe_image_hnsw 
            ON ai_productembedding 
            USING hnsw (image_vector vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """,
            reverse_sql="DROP INDEX IF EXISTS ai_pe_image_hnsw"
        ),
        migrations.RunSQL(
            """
            CREATE INDEX ai_pe_text_hnsw 
            ON ai_productembedding 
            USING hnsw (text_vector vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """,
            reverse_sql="DROP INDEX IF EXISTS ai_pe_text_hnsw"
        ),
    ]
