from django.db import migrations
# pyrefly: ignore [missing-import]
import pgvector.django


def migrate_json_to_vector(apps, schema_editor):
    """Migrate data from JSONField to VectorField."""
    ProductEmbedding = apps.get_model('ai', 'ProductEmbedding')
    for embedding in ProductEmbedding.objects.all():
        if embedding.image_vector:
            embedding.image_vector_vec = embedding.image_vector
        if embedding.text_vector:
            embedding.text_vector_vec = embedding.text_vector
        if embedding.combined_vector:
            embedding.combined_vector_vec = embedding.combined_vector
        embedding.save()


def migrate_vector_to_json(apps, schema_editor):
    """Reverse migration: migrate data from VectorField back to JSONField."""
    ProductEmbedding = apps.get_model('ai', 'ProductEmbedding')
    for embedding in ProductEmbedding.objects.all():
        if embedding.image_vector_vec:
            embedding.image_vector = list(embedding.image_vector_vec)
        if embedding.text_vector_vec:
            embedding.text_vector = list(embedding.text_vector_vec)
        if embedding.combined_vector_vec:
            embedding.combined_vector = list(embedding.combined_vector_vec)
        embedding.save()


class Migration(migrations.Migration):
    dependencies = [
        ('ai', '0001_initial_ai_models'),
    ]
    
    operations = [
        # Ensure pgvector extension is created first
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector"
        ),
        # Add VectorField columns alongside JSONField columns
        migrations.AddField(
            model_name='productembedding',
            name='image_vector_vec',
            field=pgvector.django.VectorField(dimensions=512, null=True),
        ),
        migrations.AddField(
            model_name='productembedding',
            name='text_vector_vec',
            field=pgvector.django.VectorField(dimensions=512, null=True),
        ),
        migrations.AddField(
            model_name='productembedding',
            name='combined_vector_vec',
            field=pgvector.django.VectorField(dimensions=512, null=True),
        ),
        # Migrate data from JSONField to VectorField
        migrations.RunPython(
            migrate_json_to_vector,
            reverse_code=migrate_vector_to_json,
        ),
        # Remove old JSONField columns
        migrations.RemoveField(
            model_name='productembedding',
            name='image_vector',
        ),
        migrations.RemoveField(
            model_name='productembedding',
            name='text_vector',
        ),
        migrations.RemoveField(
            model_name='productembedding',
            name='combined_vector',
        ),
        # Rename VectorField columns to original names
        migrations.RenameField(
            model_name='productembedding',
            old_name='image_vector_vec',
            new_name='image_vector',
        ),
        migrations.RenameField(
            model_name='productembedding',
            old_name='text_vector_vec',
            new_name='text_vector',
        ),
        migrations.RenameField(
            model_name='productembedding',
            old_name='combined_vector_vec',
            new_name='combined_vector',
        ),
    ]
