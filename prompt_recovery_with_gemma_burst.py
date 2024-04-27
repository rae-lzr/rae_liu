import os
os.environ["KERAS_BACKEND"] = "jax" # you can also use tensorflow or torch
os.environ["XLA_PYTHON_CLIENT_MEM_FRACTION"] = "1.00" # avoid memory fragmentation on JAX backend.

import keras
import keras_nlp

import numpy as np
import pandas as pd
from tqdm.notebook import tqdm
tqdm.pandas() # progress bar for pandas

import plotly.graph_objs as go
import plotly.express as px
from IPython.display import display, Markdown

"""# Configuration"""
from configurations.cfg import CFG

"""# Reproducibility
Sets value for random seed to produce similar result in each run.
"""

keras.utils.set_random_seed(CFG.seed)

"""# Data

No training data is provided in this competition; in other words, we can use any openly available datasets for this competition. In this notebook, we will use two external datasets that utilize the **Gemma 7B** model to transform texts using prompts.

**Data Format:**

These datasets includes:
- `original_text`: Input text/essay that needs to be transformed.
- `rewrite_prompt`: Prompt/Instruction that was used in the Gemma LM to transform `original_text`. This is also our **target** for this competition.
- `rewritten_text`: Output text that was generated by the Gemma model.
"""

# Rewritten texts
df = pd.read_csv(CFG.input_dataset_path)

"""# Prompt Engineering

Here's a simple prompt template we'll use to create instruction-response pairs from the `original_text`, `rewritten_text`, and `rewritten_prompt`:

```
Instruction:
Below, the `Original Text` passage has been rewritten/transformed/improved into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the "Original Text" and "Rewritten Text", and try to infer the specific prompt or instruction that was likely given to the LLM to rewrite/transform/improve the text in this way.

Original Text:
...

Rewritten Text:
...

Response:
...
```

This template will help the model to follow instruction and respond accurately. You can explore more advanced prompt templates for better results.
"""

template = """Instruction:\nBelow, the `Original Text` passage has been rewritten/transformed/improved into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the `Original Text` and `Rewritten Text`, and try to infer the specific prompt or instruction that was likely given to the LLM to rewrite/transform/improve the text in this way.\n\nOriginal Text:\n{original_text}\n\nRewriten Text:\n{rewritten_text}\n\nResponse:\n{rewrite_prompt}"""

# template2 = """Instruction:\nBelow, the `Original Text` passage has been summarized/paraphrased/expanded/simplified into `Rewritten Text` by the `Gemma 7b-it` LLM with a certain prompt/instruction. Your task is to carefully analyze the differences between the `Original Text` and `Rewritten Text`, and try to infer the specific prompt or instruction that was likely given to the LLM to summarize/paraphrase/expand/simplify the text in this way.\n\nOriginal Text:\n{original_text}\n\nRewriten Text:\n{rewritten_text}\n\nResponse:\n{rewrite_prompt}"""

df["prompt"] = df.progress_apply(lambda row: template.format(original_text=row.original_text,
                                                             rewritten_text=row.rewritten_text,
                                                             rewrite_prompt=row.rewrite_prompt), axis=1)
data = df.prompt.tolist()

"""Let's examine a sample prompt. As the answers in our dataset are curated with **markdown** format, we will render the sample using `Markdown()` to properly visualize the formatting.

## Sample
"""

def colorize_text(text):
    for word, color in zip(["Instruction", "Original Text", "Rewriten Text", "Response"],
                           ["red", "yellow", "blue", "green"]):
        text = text.replace(f"{word}:", f"\n\n**<font color='{color}'>{word}:</font>**")
    return text

# # Take a random sample
# sample = data[10]

# # Give colors to Instruction, Response and Category
# sample = colorize_text(sample)

# # Show sample in markdown
# display(Markdown(sample))

"""# Modeling
"""

gemma_lm = keras_nlp.models.GemmaCausalLM.from_preset(CFG.preset)
# gemma_lm.summary()

"""## Gemma LM Preprocessor
"""

x, y, sample_weight = gemma_lm.preprocessor(data)

"""This preprocessing layer will take in batches of strings, and return outputs in a `(x, y, sample_weight)` format, where the `y` label is the next token id in the `x` sequence.

From the code below, we can see that, after the preprocessor, the data shape is `(num_samples, sequence_length)`.
"""

# # Display the shape of each processed output
# for k, v in x.items():
#     print(k, ":", v.shape)

"""# Inference before Fine-Tuning

Before we do fine-tuning, let's try to recover the prompt using the Gemma model with some prepared prompts and see how it responds.

> As this model is not yet fine-tuned for instruction, you will notice that the model's responses are inaccurate.

## Sample 1
"""

# # Take one sample
# row = df.iloc[10]

# # Generate Prompt using template
# prompt = template.format(
#     original_text=row.original_text,
#     rewritten_text=row.rewritten_text,
#     rewrite_prompt="",
# )

# # Infer
# output = gemma_lm.generate(prompt, max_length=512)

# # Colorize
# output = colorize_text(output)

# # Display in markdown
# display(Markdown(output))

"""## Sample 2"""

# # Take one sample
# row = df.iloc[20]

# # Generate Prompt using template
# prompt = template.format(
#     original_text=row.original_text,
#     rewritten_text=row.rewritten_text,
#     rewrite_prompt="",
# )

# # Infer
# output = gemma_lm.generate(prompt, max_length=512)

# # Colorize
# output = colorize_text(output)

# # Display in markdown
# display(Markdown(output))

"""# Fine-tuning with LoRA
"""

# Enable LoRA for the model and set the LoRA rank to 4.
gemma_lm.backbone.enable_lora(rank=4)
# gemma_lm.summary()

"""**Notice** that, the number of trainable parameters is reduced from ~$2.5$ billions to ~$1.3$ millions after enabling LoRA.

## Training
"""

# Limit the input sequence length to 512 (to control memory usage).
gemma_lm.preprocessor.sequence_length = CFG.sequence_length

# Compile the model with loss, optimizer, and metric
gemma_lm.compile(
    loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),
    optimizer=keras.optimizers.Adam(learning_rate=3e-5),
    weighted_metrics=[keras.metrics.SparseCategoricalAccuracy()],
)

# Train model
gemma_lm.fit(data, epochs=CFG.epochs, batch_size=CFG.batch_size)

base_filename, _ = os.path.splitext(CFG.input_file_name)
gemma_lm.save(os.path.join(CFG.dataset_path, f'finetune_{CFG.preset}_{base_filename}_epoch{CFG.epochs}.keras'))

"""# Inference after fine-tuning

Let's see how our fine-tuned model responds to the same questions we asked before fine-tuning the model.

## Sample 1
"""

# # Take one sample
# row = df.iloc[10]

# # Generate Prompt using template
# prompt = template.format(
#     original_text=row.original_text,
#     rewritten_text=row.rewritten_text,
#     rewrite_prompt="",
# )

# # Infer
# output = gemma_lm.generate(prompt, max_length=512)

# # Colorize
# output = colorize_text(output)

# # Display in markdown
# display(Markdown(output))

"""## Sample 2"""

# # Take one sample
# row = df.iloc[20]

# # Generate Prompt using template
# prompt = template.format(
#     original_text=row.original_text,
#     rewritten_text=row.rewritten_text,
#     rewrite_prompt="",
# )

# # Infer
# output = gemma_lm.generate(prompt, max_length=512)

# # Colorize
# output = colorize_text(output)

# # Display in markdown
# display(Markdown(output))

# """# Test Data"""

# test_df = pd.read_csv("/kaggle/input/llm-prompt-recovery/test.csv")
# test_df['original_text'] = test_df['original_text'].fillna("")
# test_df['rewritten_text'] = test_df['rewritten_text'].fillna("")
# test_df.head()

# """## Test Sample

# Now, let's try out a sample from test data that model hasn't seen during training.
# """

# row = test_df.iloc[0]

# # Generate Prompt using template
# prompt = template.format(
#     original_text=row.original_text,
#     rewritten_text=row.rewritten_text,
#     rewrite_prompt="",
# )

# # Infer
# output = gemma_lm.generate(prompt, max_length=512)

# # Colorize
# output = colorize_text(output)

# # Display in markdown
# display(Markdown(output))

# """# Submission"""

# preds = []
# for i in tqdm(range(len(test_df))):
#     row = test_df.iloc[i]

#     # Generate Prompt using template
#     prompt = template.format(
#         original_text=row.original_text,
#         rewritten_text=row.rewritten_text,
#         rewrite_prompt=""
#     )

#     # Infer
#     output = gemma_lm.generate(prompt, max_length=512)
#     pred = output.replace(prompt, "") # remove the prompt from output

#     # Store predictions
#     preds.append([row.id, pred])

# """While preparing the submission file, we must keep in mind that, leaving any `rewrite_prompt` blank as null answers will throw an error."""

# sub_df = pd.DataFrame(preds, columns=["id", "rewrite_prompt"])
# sub_df['rewrite_prompt'] = sub_df['rewrite_prompt'].fillna("")
# sub_df['rewrite_prompt'] = sub_df['rewrite_prompt'].map(lambda x: "Improve the essay" if len(x) == 0 else x)
# sub_df.to_csv("submission.csv",index=False)
# sub_df.head()

# """# Conclusion

# The result is pretty good. Still there is ample room for improvement. Here are some tips to improve performance:

# - Try using the larger version of **Gemma** (7B).
# - Increase `sequence_length`.
# - Experiment with advanced prompt engineering techniques.
# - Implement augmentation to increase the number of samples.
# - Utilize a learning rate scheduler.

# # Reference
# * [Fine-tune Gemma models in Keras using LoRA](https://www.kaggle.com/code/nilaychauhan/fine-tune-gemma-models-in-keras-using-lora)
# * [Parameter-efficient fine-tuning of GPT-2 with LoRA](https://keras.io/examples/nlp/parameter_efficient_finetuning_of_gpt2_with_lora/)
# * [Gemma - KerasNLP](https://keras.io/api/keras_nlp/models/gemma/)
# """